from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from extensions import db
from models import Empenho, ItemEmpenho, NotaFiscal, Pregao, SaidaFinanceira
from datetime import datetime, date
from sqlalchemy import func
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'licitacao-sistema-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///licitacao.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()


def parse_date(s):
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_float(s):
    if not s:
        return 0.0
    try:
        return float(str(s).replace(',', '.').replace('R$', '').strip())
    except (ValueError, TypeError):
        return 0.0


# ──────────────────────── DASHBOARD ────────────────────────

@app.route('/')
def dashboard():
    total_empenhos = Empenho.query.count()
    empenhos = Empenho.query.all()

    total_venda = sum(e.total_venda for e in empenhos)
    total_custo = sum(e.total_custo for e in empenhos)
    lucro_total = total_venda - total_custo

    total_pendente = sum(e.total_pendente for e in empenhos)
    total_pago = sum(e.total_pago for e in empenhos)

    itens_custo_alto = ItemEmpenho.query.filter(
        ItemEmpenho.valor_custo > ItemEmpenho.valor_venda,
        ItemEmpenho.valor_venda > 0
    ).count()

    pregoes_agendados = Pregao.query.filter_by(status='AGENDADO').count()

    itens_pendentes = ItemEmpenho.query.filter(
        ItemEmpenho.situacao_entrega != 'ENTREGUE'
    ).count()

    empenhos_recentes = Empenho.query.order_by(Empenho.created_at.desc()).limit(5).all()
    pregoes_proximos = Pregao.query.filter_by(status='AGENDADO').order_by(Pregao.data_horario).limit(5).all()

    # monthly chart data
    meses_labels = []
    meses_venda = []
    meses_custo = []
    from calendar import month_abbr
    hoje = date.today()
    for m in range(5, 0, -1):
        mes = hoje.month - m
        ano = hoje.year
        if mes <= 0:
            mes += 12
            ano -= 1
        nfs = NotaFiscal.query.filter(
            func.strftime('%Y', NotaFiscal.data) == str(ano),
            func.strftime('%m', NotaFiscal.data) == f'{mes:02d}'
        ).all()
        meses_labels.append(f'{mes:02d}/{ano}')
        meses_venda.append(round(sum(n.valor for n in nfs if n.situacao != 'CANCELADA'), 2))
        meses_custo.append(0)

    return render_template('dashboard.html',
        total_empenhos=total_empenhos,
        total_venda=total_venda,
        total_custo=total_custo,
        lucro_total=lucro_total,
        total_pendente=total_pendente,
        total_pago=total_pago,
        itens_custo_alto=itens_custo_alto,
        pregoes_agendados=pregoes_agendados,
        itens_pendentes=itens_pendentes,
        empenhos_recentes=empenhos_recentes,
        pregoes_proximos=pregoes_proximos,
        meses_labels=meses_labels,
        meses_venda=meses_venda,
    )


# ──────────────────────── EMPENHOS ────────────────────────

@app.route('/empenhos')
def empenhos_index():
    q = request.args.get('q', '').strip()
    status = request.args.get('status', '')
    query = Empenho.query
    if q:
        query = query.filter(
            Empenho.numero.ilike(f'%{q}%') |
            Empenho.orgao.ilike(f'%{q}%') |
            Empenho.objeto.ilike(f'%{q}%')
        )
    empenhos = query.order_by(Empenho.created_at.desc()).all()
    if status:
        empenhos = [e for e in empenhos if e.situacao_geral == status]
    return render_template('empenhos/index.html', empenhos=empenhos, q=q, status=status)


@app.route('/empenhos/novo', methods=['GET', 'POST'])
def empenho_novo():
    if request.method == 'POST':
        emp = Empenho(
            numero=request.form['numero'],
            orgao=request.form.get('orgao', ''),
            uasg=request.form.get('uasg', ''),
            objeto=request.form.get('objeto', ''),
            data_emissao=parse_date(request.form.get('data_emissao')),
        )
        db.session.add(emp)
        db.session.commit()
        flash('Empenho criado com sucesso!', 'success')
        return redirect(url_for('empenho_detalhe', id=emp.id))
    return render_template('empenhos/form.html', empenho=None)


@app.route('/empenhos/<int:id>')
def empenho_detalhe(id):
    emp = Empenho.query.get_or_404(id)
    return render_template('empenhos/detalhe.html', empenho=emp)


@app.route('/empenhos/<int:id>/editar', methods=['GET', 'POST'])
def empenho_editar(id):
    emp = Empenho.query.get_or_404(id)
    if request.method == 'POST':
        emp.numero = request.form['numero']
        emp.orgao = request.form.get('orgao', '')
        emp.uasg = request.form.get('uasg', '')
        emp.objeto = request.form.get('objeto', '')
        emp.data_emissao = parse_date(request.form.get('data_emissao'))
        db.session.commit()
        flash('Empenho atualizado!', 'success')
        return redirect(url_for('empenho_detalhe', id=emp.id))
    return render_template('empenhos/form.html', empenho=emp)


@app.route('/empenhos/<int:id>/excluir', methods=['POST'])
def empenho_excluir(id):
    emp = Empenho.query.get_or_404(id)
    db.session.delete(emp)
    db.session.commit()
    flash('Empenho excluído!', 'warning')
    return redirect(url_for('empenhos_index'))


# ──────────────────────── ITENS ────────────────────────

@app.route('/empenhos/<int:empenho_id>/itens/novo', methods=['GET', 'POST'])
def item_novo(empenho_id):
    emp = Empenho.query.get_or_404(empenho_id)
    if request.method == 'POST':
        item = ItemEmpenho(
            empenho_id=empenho_id,
            item_nome=request.form['item_nome'],
            unidade=request.form.get('unidade', ''),
            marca=request.form.get('marca', ''),
            quantidade=parse_float(request.form.get('quantidade')),
            valor_venda=parse_float(request.form.get('valor_venda')),
            quantidade_entregue=parse_float(request.form.get('quantidade_entregue')),
            valor_custo=parse_float(request.form.get('valor_custo')),
            situacao_entrega=request.form.get('situacao_entrega', 'FALTA ENTREGAR'),
            observacao=request.form.get('observacao', ''),
            responsavel_compra=request.form.get('responsavel_compra', ''),
            responsavel_entrega=request.form.get('responsavel_entrega', ''),
        )
        db.session.add(item)
        db.session.commit()
        flash('Item adicionado!', 'success')
        return redirect(url_for('empenho_detalhe', id=empenho_id))
    return render_template('empenhos/item_form.html', empenho=emp, item=None)


@app.route('/itens/<int:id>/editar', methods=['GET', 'POST'])
def item_editar(id):
    item = ItemEmpenho.query.get_or_404(id)
    if request.method == 'POST':
        item.item_nome = request.form['item_nome']
        item.unidade = request.form.get('unidade', '')
        item.marca = request.form.get('marca', '')
        item.quantidade = parse_float(request.form.get('quantidade'))
        item.valor_venda = parse_float(request.form.get('valor_venda'))
        item.quantidade_entregue = parse_float(request.form.get('quantidade_entregue'))
        item.valor_custo = parse_float(request.form.get('valor_custo'))
        item.situacao_entrega = request.form.get('situacao_entrega', 'FALTA ENTREGAR')
        item.observacao = request.form.get('observacao', '')
        item.responsavel_compra = request.form.get('responsavel_compra', '')
        item.responsavel_entrega = request.form.get('responsavel_entrega', '')
        db.session.commit()
        flash('Item atualizado!', 'success')
        return redirect(url_for('empenho_detalhe', id=item.empenho_id))
    return render_template('empenhos/item_form.html', empenho=item.empenho, item=item)


@app.route('/itens/<int:id>/excluir', methods=['POST'])
def item_excluir(id):
    item = ItemEmpenho.query.get_or_404(id)
    empenho_id = item.empenho_id
    db.session.delete(item)
    db.session.commit()
    flash('Item excluído!', 'warning')
    return redirect(url_for('empenho_detalhe', id=empenho_id))


# ──────────────────────── NOTAS FISCAIS ────────────────────────

@app.route('/empenhos/<int:empenho_id>/notas/nova', methods=['GET', 'POST'])
def nota_nova(empenho_id):
    emp = Empenho.query.get_or_404(empenho_id)
    if request.method == 'POST':
        item_id = request.form.get('item_id') or None
        nf = NotaFiscal(
            empenho_id=empenho_id,
            item_id=int(item_id) if item_id else None,
            numero=request.form.get('numero', ''),
            valor=parse_float(request.form.get('valor')),
            data=parse_date(request.form.get('data')),
            situacao=request.form.get('situacao', 'PENDENTE'),
            observacao=request.form.get('observacao', ''),
        )
        db.session.add(nf)
        db.session.commit()
        flash('Nota Fiscal registrada!', 'success')
        return redirect(url_for('empenho_detalhe', id=empenho_id))
    return render_template('empenhos/nota_form.html', empenho=emp, nota=None)


@app.route('/notas/<int:id>/editar', methods=['GET', 'POST'])
def nota_editar(id):
    nf = NotaFiscal.query.get_or_404(id)
    if request.method == 'POST':
        nf.numero = request.form.get('numero', '')
        nf.item_id = int(request.form.get('item_id')) if request.form.get('item_id') else None
        nf.valor = parse_float(request.form.get('valor'))
        nf.data = parse_date(request.form.get('data'))
        nf.situacao = request.form.get('situacao', 'PENDENTE')
        nf.observacao = request.form.get('observacao', '')
        db.session.commit()
        flash('Nota Fiscal atualizada!', 'success')
        return redirect(url_for('empenho_detalhe', id=nf.empenho_id))
    return render_template('empenhos/nota_form.html', empenho=nf.empenho, nota=nf)


@app.route('/notas/<int:id>/excluir', methods=['POST'])
def nota_excluir(id):
    nf = NotaFiscal.query.get_or_404(id)
    empenho_id = nf.empenho_id
    db.session.delete(nf)
    db.session.commit()
    flash('Nota Fiscal excluída!', 'warning')
    return redirect(url_for('empenho_detalhe', id=empenho_id))


@app.route('/notas/<int:id>/pagar', methods=['POST'])
def nota_pagar(id):
    nf = NotaFiscal.query.get_or_404(id)
    nf.situacao = 'PAGO'
    db.session.commit()
    return jsonify({'ok': True})


# ──────────────────────── PREGÕES ────────────────────────

@app.route('/pregoes')
def pregoes_index():
    q = request.args.get('q', '').strip()
    status = request.args.get('status', '')
    query = Pregao.query
    if q:
        query = query.filter(
            Pregao.orgao.ilike(f'%{q}%') |
            Pregao.objeto.ilike(f'%{q}%') |
            Pregao.uasg.ilike(f'%{q}%')
        )
    if status:
        query = query.filter_by(status=status)
    pregoes = query.order_by(Pregao.data_horario.asc()).all()
    return render_template('pregoes/index.html', pregoes=pregoes, q=q, status=status)


@app.route('/pregoes/novo', methods=['GET', 'POST'])
def pregao_novo():
    if request.method == 'POST':
        dt = request.form.get('data_horario', '')
        data_horario = None
        if dt:
            try:
                data_horario = datetime.strptime(dt, '%Y-%m-%dT%H:%M')
            except ValueError:
                try:
                    data_horario = datetime.strptime(dt, '%Y-%m-%d')
                except ValueError:
                    pass
        p = Pregao(
            orgao=request.form['orgao'],
            forma=request.form.get('forma', ''),
            uasg=request.form.get('uasg', ''),
            data_horario=data_horario,
            objeto=request.form.get('objeto', ''),
            valor=parse_float(request.form.get('valor')),
            exige_atestado=request.form.get('exige_atestado') == '1',
            percentagem_atestado=parse_float(request.form.get('percentagem_atestado')) or None,
            exige_garantia=request.form.get('exige_garantia') == '1',
            responsavel=request.form.get('responsavel', ''),
            lote_ou_und=request.form.get('lote_ou_und', ''),
            qtd_itens=int(request.form.get('qtd_itens') or 0) or None,
            status=request.form.get('status', 'AGENDADO'),
            observacao=request.form.get('observacao', ''),
        )
        db.session.add(p)
        db.session.commit()
        flash('Pregão registrado!', 'success')
        return redirect(url_for('pregoes_index'))
    return render_template('pregoes/form.html', pregao=None)


@app.route('/pregoes/<int:id>/editar', methods=['GET', 'POST'])
def pregao_editar(id):
    p = Pregao.query.get_or_404(id)
    if request.method == 'POST':
        dt = request.form.get('data_horario', '')
        data_horario = None
        if dt:
            try:
                data_horario = datetime.strptime(dt, '%Y-%m-%dT%H:%M')
            except ValueError:
                try:
                    data_horario = datetime.strptime(dt, '%Y-%m-%d')
                except ValueError:
                    pass
        p.orgao = request.form['orgao']
        p.forma = request.form.get('forma', '')
        p.uasg = request.form.get('uasg', '')
        p.data_horario = data_horario
        p.objeto = request.form.get('objeto', '')
        p.valor = parse_float(request.form.get('valor'))
        p.exige_atestado = request.form.get('exige_atestado') == '1'
        p.percentagem_atestado = parse_float(request.form.get('percentagem_atestado')) or None
        p.exige_garantia = request.form.get('exige_garantia') == '1'
        p.responsavel = request.form.get('responsavel', '')
        p.lote_ou_und = request.form.get('lote_ou_und', '')
        p.qtd_itens = int(request.form.get('qtd_itens') or 0) or None
        p.status = request.form.get('status', 'AGENDADO')
        p.observacao = request.form.get('observacao', '')
        db.session.commit()
        flash('Pregão atualizado!', 'success')
        return redirect(url_for('pregoes_index'))
    return render_template('pregoes/form.html', pregao=p)


@app.route('/pregoes/<int:id>/excluir', methods=['POST'])
def pregao_excluir(id):
    p = Pregao.query.get_or_404(id)
    db.session.delete(p)
    db.session.commit()
    flash('Pregão excluído!', 'warning')
    return redirect(url_for('pregoes_index'))


# ──────────────────────── FINANCEIRO ────────────────────────

@app.route('/financeiro')
def financeiro_index():
    mes = request.args.get('mes', date.today().strftime('%Y-%m'))
    try:
        ano, m = int(mes.split('-')[0]), int(mes.split('-')[1])
    except Exception:
        ano, m = date.today().year, date.today().month

    saidas = SaidaFinanceira.query.filter(
        func.strftime('%Y', SaidaFinanceira.data) == str(ano),
        func.strftime('%m', SaidaFinanceira.data) == f'{m:02d}'
    ).order_by(SaidaFinanceira.data).all()

    notas_mes = NotaFiscal.query.filter(
        func.strftime('%Y', NotaFiscal.data) == str(ano),
        func.strftime('%m', NotaFiscal.data) == f'{m:02d}'
    ).all()

    total_saidas = sum(s.valor for s in saidas)
    total_recebido = sum(n.valor for n in notas_mes if n.situacao == 'PAGO')
    total_pendente = sum(n.valor for n in notas_mes if n.situacao == 'PENDENTE')
    saldo = total_recebido - total_saidas

    todas_saidas = SaidaFinanceira.query.order_by(SaidaFinanceira.data.desc()).all()

    return render_template('financeiro/index.html',
        saidas=saidas,
        notas_mes=notas_mes,
        total_saidas=total_saidas,
        total_recebido=total_recebido,
        total_pendente=total_pendente,
        saldo=saldo,
        mes=mes,
        todas_saidas=todas_saidas,
    )


@app.route('/financeiro/saida/nova', methods=['POST'])
def saida_nova():
    s = SaidaFinanceira(
        data=parse_date(request.form.get('data')),
        valor=parse_float(request.form.get('valor')),
        destino=request.form.get('destino', ''),
        observacao=request.form.get('observacao', ''),
    )
    db.session.add(s)
    db.session.commit()
    flash('Saída registrada!', 'success')
    return redirect(url_for('financeiro_index'))


@app.route('/financeiro/saida/<int:id>/excluir', methods=['POST'])
def saida_excluir(id):
    s = SaidaFinanceira.query.get_or_404(id)
    db.session.delete(s)
    db.session.commit()
    flash('Saída excluída!', 'warning')
    return redirect(url_for('financeiro_index'))


# ──────────────────────── API JSON ────────────────────────

@app.route('/api/empenho/<int:id>/totais')
def api_empenho_totais(id):
    emp = Empenho.query.get_or_404(id)
    return jsonify({
        'total_venda': emp.total_venda,
        'total_custo': emp.total_custo,
        'lucro': emp.lucro_total,
        'total_pendente': emp.total_pendente,
        'total_pago': emp.total_pago,
    })


@app.template_filter('brl')
def brl_filter(value):
    try:
        return f'R$ {float(value):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    except (TypeError, ValueError):
        return 'R$ 0,00'


@app.template_filter('fmt_date')
def fmt_date_filter(value):
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%d/%m/%Y')
    return str(value)


@app.template_filter('fmt_datetime')
def fmt_datetime_filter(value):
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime('%d/%m/%Y %H:%M')
    return str(value)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
