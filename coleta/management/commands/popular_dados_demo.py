import random
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from autenticacao.models import Usuario
from catalogo.models import Operador, Variavel
from estudos.models import Criterio, Estudo
from coleta.models import Participacao, Voluntario
from coleta.seguranca import cifrar, identificador_cpf


TOTAL_ESTUDOS = 500
TOTAL_VOLUNTARIOS = 5000
MARCADOR = "DEMONSTRAÇÃO FICTÍCIA"

CONDICOES = [
    "Saúde cardiovascular", "Qualidade do sono", "Alimentação e bem-estar", "Atividade física",
    "Saúde respiratória", "Atenção primária", "Saúde da pessoa idosa", "Saúde materna",
    "Saúde mental e rotina", "Acesso a serviços de saúde", "Reabilitação funcional", "Hábitos de prevenção",
    "Saúde ocupacional", "Mobilidade e qualidade de vida", "Educação em saúde", "Condições crônicas",
    "Uso de serviços preventivos", "Bem-estar em comunidades", "Hábitos de hidratação", "Autocuidado",
]
OBJETIVOS = [
    "descrever padrões autorrelatados de saúde e bem-estar em diferentes grupos adultos",
    "acompanhar indicadores gerais de qualidade de vida em participantes voluntários",
    "explorar a relação entre hábitos cotidianos e indicadores de saúde autorrelatados",
    "avaliar a experiência de participantes no acesso a ações de promoção da saúde",
    "identificar necessidades de informação e prevenção relatadas pelos participantes",
    "observar a evolução de indicadores não identificáveis ao longo do acompanhamento",
]
METODOS = [
    "A coleta é observacional e realizada por profissionais autorizados, seguindo os critérios definidos no sistema.",
    "O acompanhamento utiliza formulários estruturados e registros vinculados à participação no estudo.",
    "A equipe registra somente as variáveis previstas no protocolo e acompanha a elegibilidade dos participantes.",
    "O protocolo prevê coleta padronizada, revisão dos registros e acompanhamento periódico da participação.",
]
PRIMEIROS_NOMES = [
    "Ana", "Bruno", "Camila", "Daniel", "Eduarda", "Felipe", "Gabriela", "Henrique", "Isabela", "João",
    "Karen", "Lucas", "Mariana", "Nicolas", "Olivia", "Pedro", "Rafaela", "Samuel", "Talita", "Victor",
]
SOBRENOMES = [
    "Almeida", "Barbosa", "Cardoso", "Dias", "Esteves", "Ferreira", "Gomes", "Lima", "Martins", "Nogueira",
    "Oliveira", "Pereira", "Queiroz", "Ribeiro", "Santos", "Teixeira", "Vieira", "Xavier", "Araújo", "Costa",
]


def cpf_valido(base):
    digitos = [int(digito) for digito in f"{base:09d}"]
    for quantidade, peso_inicial in ((9, 10), (10, 11)):
        soma = sum(numero * peso for numero, peso in zip(digitos[:quantidade], range(peso_inicial, 1, -1)))
        verificador = (soma * 10) % 11
        digitos.append(0 if verificador == 10 else verificador)
    return "".join(map(str, digitos))


def lotes(itens, tamanho=400):
    for inicio in range(0, len(itens), tamanho):
        yield itens[inicio:inicio + tamanho]


class Command(BaseCommand):
    help = "Insere um conjunto idempotente de dados fictícios para demonstração do DataCampus."

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=2611, help="Semente para gerar dados reproduzíveis.")
        parser.add_argument(
            "--sem-participacoes", action="store_true",
            help="Cria estudos e voluntários sem gerar os vínculos usados nos painéis.",
        )

    def handle(self, *args, **options):
        rng = random.Random(options["seed"])
        pesquisadores = list(Usuario.objects.filter(perfil=Usuario.Perfil.PESQUISADOR).order_by("pk"))
        if not pesquisadores:
            raise CommandError("Cadastre ao menos um pesquisador antes de carregar os dados de demonstração.")
        profissionais = list(Usuario.objects.filter(perfil=Usuario.Perfil.PROFISSIONAL).order_by("pk"))

        chave_fernet = getattr(settings, "DATACAMPUS_FERNET_KEY", "")
        chave_hmac = getattr(settings, "DATACAMPUS_HMAC_KEY", "")
        if not chave_fernet or len(chave_hmac.encode("utf-8")) < 32:
            raise CommandError("Configure DATACAMPUS_FERNET_KEY e DATACAMPUS_HMAC_KEY no ambiente.")

        try:
            variavel_idade = Variavel.objects.get(codigo="idade_anos", tipo=Variavel.Tipo.NUMERICA)
        except Variavel.DoesNotExist as erro:
            raise CommandError("O catálogo precisa conter a variável numérica idade_anos.") from erro

        agora = timezone.now()
        nomes_estudos = [f"{MARCADOR} — Pesquisa {numero:03d}" for numero in range(1, TOTAL_ESTUDOS + 1)]
        existentes_estudos = {item.nome: item for item in Estudo.objects.filter(nome__in=nomes_estudos)}
        novos_estudos = []
        for numero, nome in enumerate(nomes_estudos, start=1):
            if nome in existentes_estudos:
                continue
            condicao = rng.choice(CONDICOES)
            objetivo = rng.choice(OBJETIVOS)
            descricao = (
                f"{MARCADOR}. Este registro contém conteúdo sintético e não descreve pesquisa real.\n\n"
                f"Objetivo: {objetivo}. O tema de referência é {condicao.lower()}.\n\n"
                f"Procedimento: {rng.choice(METODOS)} Os dados servem somente para demonstração da navegação, "
                "dos indicadores e dos filtros do DataCampus; não devem orientar decisões clínicas.\n\n"
                "A participação é representada por registros fictícios, sem respostas clínicas ou dados de pessoas reais."
            )
            situacao = rng.choices(
                [Estudo.Situacao.ATIVO, Estudo.Situacao.RASCUNHO, Estudo.Situacao.ENCERRADO],
                weights=[70, 20, 10], k=1,
            )[0]
            criacao = agora - timedelta(days=rng.randint(0, 364), hours=rng.randint(0, 23))
            novos_estudos.append(Estudo(
                nome=nome,
                condicao=condicao,
                descricao=descricao,
                situacao=situacao,
                participantes_necessarios=rng.randint(30, 500),
                pesquisador=rng.choice(pesquisadores),
                criado_em=criacao,
            ))

        nomes_voluntarios = [f"{MARCADOR} — Voluntário {numero:05d}" for numero in range(1, TOTAL_VOLUNTARIOS + 1)]
        # CPFs válidos gerados por sequência determinística; nunca são dados de pessoas reais.
        cpf_por_numero = {numero: cpf_valido(100_000_000 + numero) for numero in range(1, TOTAL_VOLUNTARIOS + 1)}
        identificador_por_numero = {numero: identificador_cpf(cpf) for numero, cpf in cpf_por_numero.items()}
        identificadores = list(identificador_por_numero.values())
        existentes_voluntarios = {}
        for lote in lotes(identificadores):
            existentes_voluntarios.update({
                item.identificador: item
                for item in Voluntario.objects.filter(identificador__in=lote)
            })

        novas_pesquisas = 0
        novos_voluntarios = 0
        novos_criterios = 0
        novas_participacoes = 0

        with transaction.atomic():
            if novos_estudos:
                Estudo.objects.bulk_create(novos_estudos, batch_size=250)
            estudos_demo = list(Estudo.objects.filter(nome__in=nomes_estudos).order_by("nome"))
            novas_pesquisas = len(novos_estudos)

            criterios_existentes = set(Criterio.objects.filter(
                estudo__in=estudos_demo, variavel=variavel_idade
            ).values_list("estudo_id", flat=True))
            criterios = []
            for estudo in estudos_demo:
                if estudo.pk in criterios_existentes:
                    continue
                criterios.append(Criterio(
                    estudo=estudo,
                    variavel=variavel_idade,
                    operador=Operador.MAIOR_IGUAL,
                    valor_numero=rng.choice((18, 21, 25, 30)),
                ))
            if criterios:
                Criterio.objects.bulk_create(criterios, batch_size=250)
                novos_criterios = len(criterios)

            voluntarios_novos = []
            datas_criacao_voluntario = {}
            for numero in range(1, TOTAL_VOLUNTARIOS + 1):
                identificador = identificador_por_numero[numero]
                if identificador in existentes_voluntarios:
                    continue
                cpf = cpf_por_numero[numero]
                nome = f"{rng.choice(PRIMEIROS_NOMES)} {rng.choice(SOBRENOMES)} {rng.choice(SOBRENOMES)}"
                # O marcador de demonstração deixa evidente que o cadastro é fictício.
                nome = f"{MARCADOR} — {nome} {numero:05d}"
                email = f"demo-voluntario-{numero:05d}@example.invalid"
                autorizou = rng.choice((True, False))
                criado_em = agora - timedelta(days=rng.randint(0, 364), hours=rng.randint(0, 23))
                datas_criacao_voluntario[identificador] = criado_em
                voluntarios_novos.append(Voluntario(
                    identificador=identificador,
                    nome_cifrado=cifrar(nome),
                    cpf_cifrado=cifrar(cpf),
                    email_cifrado=cifrar(email),
                    autorizou_reuso_em=(criado_em if autorizou else None),
                    criado_em=criado_em,
                ))
            for lote in lotes(voluntarios_novos, 250):
                Voluntario.objects.bulk_create(lote, batch_size=250)
            novos_voluntarios = len(voluntarios_novos)

            if not options["sem_participacoes"]:
                ativos = [item for item in estudos_demo if item.situacao == Estudo.Situacao.ATIVO]
                if not ativos:
                    raise CommandError("Não há pesquisas de demonstração ativas para associar aos voluntários.")
                voluntarios_demo = []
                for lote in lotes(identificadores):
                    voluntarios_demo.extend(Voluntario.objects.filter(identificador__in=lote))
                ids_participando = set()
                ids_voluntarios = [item.pk for item in voluntarios_demo]
                for lote in lotes(ids_voluntarios):
                    ids_participando.update(Participacao.objects.filter(
                        voluntario_id__in=lote
                    ).values_list("voluntario_id", flat=True))

                participacoes = []
                for voluntario in voluntarios_demo:
                    if voluntario.pk in ids_participando:
                        continue
                    estudo = rng.choice(ativos)
                    criado_em = getattr(voluntario, "criado_em", agora)
                    vinculado_em = min(agora, criado_em + timedelta(days=rng.randint(0, 90)))
                    participacoes.append(Participacao(
                        estudo=estudo,
                        voluntario=voluntario,
                        profissional=rng.choice(profissionais) if profissionais else None,
                        situacao=Participacao.Situacao.PENDENTE,
                        criado_em=vinculado_em,
                        atualizado_em=vinculado_em,
                    ))
                for lote in lotes(participacoes, 400):
                    Participacao.objects.bulk_create(lote, batch_size=400)
                novas_participacoes = len(participacoes)

        self.stdout.write(self.style.SUCCESS(
            f"Banco {settings.DATABASES['default']['ENGINE']}: "
            f"{novas_pesquisas} pesquisas, {novos_criterios} critérios, "
            f"{novos_voluntarios} voluntários e {novas_participacoes} participações inseridos."
        ))
        self.stdout.write("Dados de demonstração identificados, sem e-mails reais e sem respostas clínicas inventadas.")
