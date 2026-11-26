from django import forms
from django.core.exceptions import ValidationError

from catalogo.models import OpcaoDominio, Variavel
from estudos.models import Estudo

from .seguranca import validar_cpf


class RegistroParticipacaoForm(forms.Form):
    estudo = forms.ModelChoiceField(queryset=Estudo.objects.none(), label="Estudo")
    nome = forms.CharField(label="Nome completo do paciente", max_length=150)
    cpf = forms.CharField(label="CPF do paciente", max_length=18)
    email = forms.EmailField(label="E-mail do voluntário (opcional)", max_length=254, required=False)
    autorizado_reuso = forms.BooleanField(
        label="O voluntário autorizou o uso dos dados em outros estudos",
        required=False,
    )

    def __init__(self, *args, usuario, **kwargs):
        super().__init__(*args, **kwargs)
        estudos = Estudo.objects.filter(situacao=Estudo.Situacao.ATIVO)
        if usuario.e_pesquisador:
            estudos = estudos.filter(pesquisador=usuario)
        self.fields["estudo"].queryset = estudos

    def clean_cpf(self):
        return validar_cpf(self.cleaned_data["cpf"])

    def clean_nome(self):
        nome = " ".join(self.cleaned_data["nome"].split())
        if len(nome) < 2:
            raise ValidationError("Informe o nome completo do paciente.")
        return nome

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_estudo(self):
        estudo = self.cleaned_data["estudo"]
        if not estudo.criterios.exists():
            raise ValidationError("O estudo precisa ter pelo menos um critério antes de iniciar a coleta.")
        return estudo


class ValoresColetaForm(forms.Form):
    def __init__(self, *args, variaveis=(), valores=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.variaveis = list(variaveis)
        valores = valores or {}
        for variavel in self.variaveis:
            inicial = valores.get(variavel.pk)
            if variavel.tipo == Variavel.Tipo.BOOLEANA and inicial is not None:
                inicial = "true" if inicial else "false"
            kwargs_campo = {"label": variavel.nome, "required": False, "initial": inicial}
            if variavel.tipo == Variavel.Tipo.NUMERICA:
                self.fields[self.chave(variavel)] = forms.DecimalField(
                    max_digits=12, decimal_places=2, min_value=variavel.minimo, max_value=variavel.maximo,
                    **kwargs_campo,
                )
            elif variavel.tipo == Variavel.Tipo.DATA:
                self.fields[self.chave(variavel)] = forms.DateField(
                    widget=forms.DateInput(attrs={"type": "date"}), **kwargs_campo
                )
            elif variavel.tipo in (Variavel.Tipo.NOMINAL, Variavel.Tipo.ORDINAL):
                self.fields[self.chave(variavel)] = forms.ModelChoiceField(
                    queryset=OpcaoDominio.objects.filter(dominio=variavel.dominio),
                    empty_label="Selecione",
                    **kwargs_campo,
                )
            elif variavel.tipo == Variavel.Tipo.BOOLEANA:
                self.fields[self.chave(variavel)] = forms.TypedChoiceField(
                    choices=(("", "Selecione"), ("true", "Sim"), ("false", "Não")),
                    coerce=lambda valor: valor == "true",
                    empty_value=None,
                    **kwargs_campo,
                )

    @staticmethod
    def chave(variavel):
        return f"variavel_{variavel.pk}"

    def clean(self):
        dados = super().clean()
        for variavel in self.variaveis:
            valor = dados.get(self.chave(variavel))
            if valor is None:
                continue
            if variavel.tipo == Variavel.Tipo.NUMERICA:
                if variavel.minimo is not None and valor < variavel.minimo:
                    self.add_error(self.chave(variavel), f"O valor mínimo é {variavel.minimo}.")
                if variavel.maximo is not None and valor > variavel.maximo:
                    self.add_error(self.chave(variavel), f"O valor máximo é {variavel.maximo}.")
        return dados


class AcessoVoluntarioForm(forms.Form):
    cpf = forms.CharField(label="CPF cadastrado", max_length=18)

    def clean_cpf(self):
        return validar_cpf(self.cleaned_data["cpf"])


class AvaliacaoVoluntarioForm(forms.Form):
    ESCOLHAS_ESTRELAS = [(n, "0" if n == 0 else "★" * n) for n in range(6)]
    nota_estudo = forms.TypedChoiceField(
        label="Como você avalia esta pesquisa?",
        choices=ESCOLHAS_ESTRELAS,
        coerce=int,
        widget=forms.RadioSelect,
    )
    nota_pesquisador = forms.TypedChoiceField(
        label="Como você avalia o pesquisador responsável?",
        choices=ESCOLHAS_ESTRELAS,
        coerce=int,
        widget=forms.RadioSelect,
    )
    comentario = forms.CharField(
        label="Comentário para o pesquisador",
        max_length=1000,
        required=False,
        help_text="Opcional. Não inclua informações de saúde nem dados pessoais neste comentário.",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Compartilhe sua experiência (opcional)."}),
    )
