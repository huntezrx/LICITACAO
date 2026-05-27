from extensions import db
from datetime import datetime


class Empenho(db.Model):
    __tablename__ = 'empenhos'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), nullable=False)
    orgao = db.Column(db.String(200))
    uasg = db.Column(db.String(50))
    objeto = db.Column(db.Text)
    data_emissao = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    itens = db.relationship('ItemEmpenho', backref='empenho', lazy=True, cascade='all, delete-orphan')
    notas_fiscais = db.relationship('NotaFiscal', backref='empenho', lazy=True, cascade='all, delete-orphan')

    @property
    def total_venda(self):
        return sum(i.valor_total_venda for i in self.itens)

    @property
    def total_custo(self):
        return sum(i.valor_total_custo for i in self.itens)

    @property
    def lucro_total(self):
        return self.total_venda - self.total_custo

    @property
    def total_pendente(self):
        return sum(nf.valor for nf in self.notas_fiscais if nf.situacao == 'PENDENTE')

    @property
    def total_pago(self):
        return sum(nf.valor for nf in self.notas_fiscais if nf.situacao == 'PAGO')

    @property
    def situacao_geral(self):
        if not self.itens:
            return 'SEM ITENS'
        entregues = [i for i in self.itens if i.situacao_entrega == 'ENTREGUE']
        parciais = [i for i in self.itens if i.situacao_entrega == 'ENTREGUE PARCIAL']
        if len(entregues) == len(self.itens):
            return 'ENTREGUE'
        elif entregues or parciais:
            return 'ENTREGUE PARCIAL'
        return 'FALTA ENTREGAR'


class ItemEmpenho(db.Model):
    __tablename__ = 'itens_empenho'

    id = db.Column(db.Integer, primary_key=True)
    empenho_id = db.Column(db.Integer, db.ForeignKey('empenhos.id'), nullable=False)
    item_nome = db.Column(db.String(200), nullable=False)
    unidade = db.Column(db.String(20))
    marca = db.Column(db.String(100))
    quantidade = db.Column(db.Float, default=0)
    valor_venda = db.Column(db.Float, default=0)
    quantidade_entregue = db.Column(db.Float, default=0)
    valor_custo = db.Column(db.Float, default=0)
    situacao_entrega = db.Column(db.String(30), default='FALTA ENTREGAR')
    observacao = db.Column(db.Text)
    responsavel_compra = db.Column(db.String(100))
    responsavel_entrega = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    notas_fiscais = db.relationship('NotaFiscal', backref='item', lazy=True)

    @property
    def valor_total_venda(self):
        return (self.quantidade or 0) * (self.valor_venda or 0)

    @property
    def valor_total_custo(self):
        return (self.quantidade or 0) * (self.valor_custo or 0)

    @property
    def lucro(self):
        return self.valor_total_venda - self.valor_total_custo

    @property
    def custo_maior_venda(self):
        return self.valor_custo > self.valor_venda if self.valor_custo and self.valor_venda else False


class NotaFiscal(db.Model):
    __tablename__ = 'notas_fiscais'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50))
    empenho_id = db.Column(db.Integer, db.ForeignKey('empenhos.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('itens_empenho.id'), nullable=True)
    valor = db.Column(db.Float, default=0)
    data = db.Column(db.Date)
    situacao = db.Column(db.String(20), default='PENDENTE')
    observacao = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Pregao(db.Model):
    __tablename__ = 'pregoes'

    id = db.Column(db.Integer, primary_key=True)
    orgao = db.Column(db.String(200), nullable=False)
    forma = db.Column(db.String(50))
    uasg = db.Column(db.String(50))
    data_horario = db.Column(db.DateTime)
    objeto = db.Column(db.Text)
    valor = db.Column(db.Float, default=0)
    exige_atestado = db.Column(db.Boolean, default=False)
    percentagem_atestado = db.Column(db.Float)
    exige_garantia = db.Column(db.Boolean, default=False)
    responsavel = db.Column(db.String(100))
    lote_ou_und = db.Column(db.String(50))
    qtd_itens = db.Column(db.Integer)
    status = db.Column(db.String(30), default='AGENDADO')
    observacao = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SaidaFinanceira(db.Model):
    __tablename__ = 'saidas_financeiras'

    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    valor = db.Column(db.Float, nullable=False)
    destino = db.Column(db.String(200))
    observacao = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
