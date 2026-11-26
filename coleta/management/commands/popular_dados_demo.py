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
    "hipertensão arterial", "diabetes mellitus tipo 2", "obesidade", "asma", "doença pulmonar obstrutiva crônica",
    "doença cardiovascular", "doença renal crônica", "osteoartrite", "osteoporose", "artrite reumatoide",
    "enxaqueca", "depressão", "transtorno de ansiedade", "apneia do sono", "anemia ferropriva",
    "doença de Parkinson", "doença de Alzheimer", "doença celíaca", "câncer de mama", "endometriose",
    "hipotireoidismo", "doença hepática gordurosa", "doença vascular periférica", "insuficiência cardíaca",
    "acidente vascular cerebral", "epilepsia", "fibromialgia", "lombalgia crônica", "rinite alérgica", "psoríase",
    "dermatite atópica", "tuberculose", "hepatite C", "infecção pelo HIV", "esclerose múltipla", "glaucoma",
    "catarata", "doença periodontal", "doença de Crohn", "colite ulcerativa", "síndrome dos ovários policísticos",
    "menopausa", "pré-diabetes", "dislipidemia", "refluxo gastroesofágico", "doença pulmonar intersticial",
    "insuficiência renal", "câncer colorretal", "leucemia", "doença falciforme",
]
FORMATOS_PESQUISA = [
    "Estudo observacional de {condicao}",
    "Perfil de saúde de pessoas com {condicao}",
    "Qualidade de vida de pessoas com {condicao}",
    "Hábitos de autocuidado em pessoas com {condicao}",
    "Acompanhamento de participantes com {condicao}",
    "Acesso aos serviços de saúde por pessoas com {condicao}",
    "Indicadores de bem-estar relacionados a {condicao}",
    "Rotina de cuidado de pessoas com {condicao}",
    "Experiência dos participantes no cuidado de {condicao}",
    "Fatores associados ao acompanhamento de {condicao}",
]
PRIMEIROS_NOMES = [
    "Ana", "Bruno", "Camila", "Daniel", "Eduarda", "Felipe", "Gabriela", "Henrique", "Isabela", "João",
    "Karen", "Lucas", "Mariana", "Nicolas", "Olivia", "Pedro", "Rafaela", "Samuel", "Talita", "Victor",
]
SOBRENOMES = [
    "Almeida", "Barbosa", "Cardoso", "Dias", "Esteves", "Ferreira", "Gomes", "Lima", "Martins", "Nogueira",
    "Oliveira", "Pereira", "Queiroz", "Ribeiro", "Santos", "Teixeira", "Vieira", "Xavier", "Araújo", "Costa",
]
NOMES_DO_MEIO = [
    "Beatriz", "Caio", "Davi", "Elisa", "Fernanda", "Gustavo", "Helena", "Igor", "Juliana", "Kaique",
    "Laura", "Miguel", "Natália", "Otávio", "Patrícia", "Renato", "Sofia", "Thiago", "Valentina", "Wesley",
]


def dados_pesquisa(numero):
    condicao = CONDICOES[(numero - 1) // len(FORMATOS_PESQUISA)]
    formato = FORMATOS_PESQUISA[(numero - 1) % len(FORMATOS_PESQUISA)]
    nome = formato.format(condicao=condicao)
    descricao = (
        f"Objetivo: descrever aspectos sociodemográficos, hábitos de saúde e experiência de acompanhamento "
        f"de participantes adultos relacionados a {condicao}.\n\n"
        "Delineamento: estudo observacional com coleta estruturada de informações autorrelatadas.\n\n"
        "População de interesse: pessoas adultas com a condição estudada. A participação depende da análise "
        "dos critérios de elegibilidade cadastrados pela equipe responsável.\n\n"
        "Acompanhamento: registro das participações e revisão dos dados coletados pela equipe. As informações "
        "devem ser analisadas de forma agregada e tratadas conforme as regras de privacidade do projeto."
    )
    return nome, condicao, descricao


def nome_voluntario(numero, rng):
    return " ".join((
        rng.choice(PRIMEIROS_NOMES), rng.choice(NOMES_DO_MEIO),
        rng.choice(SOBRENOMES), rng.choice(SOBRENOMES),
    ))


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
        dados_estudos = [dados_pesquisa(numero) for numero in range(1, TOTAL_ESTUDOS + 1)]
        nomes_estudos = [item[0] for item in dados_estudos]
        nomes_antigos = [f"{MARCADOR} — Pesquisa {numero:03d}" for numero in range(1, TOTAL_ESTUDOS + 1)]
        existentes_estudos = {item.nome: item for item in Estudo.objects.filter(nome__in=nomes_estudos)}
        estudos_antigos = {item.nome: item for item in Estudo.objects.filter(nome__in=nomes_antigos)}
        novos_estudos = []
        estudos_renomeados = []
        estudos_atualizados = []
        estudos_demo = []
        for numero, (nome, condicao, descricao) in enumerate(dados_estudos, start=1):
            if nome in existentes_estudos:
                estudo = existentes_estudos[nome]
                if "Objetivo ilustrativo:" in estudo.descricao:
                    estudo.condicao = condicao
                    estudo.descricao = descricao
                    estudos_atualizados.append(estudo)
                estudos_demo.append(estudo)
                continue
            nome_antigo = nomes_antigos[numero - 1]
            if nome_antigo in estudos_antigos:
                estudo = estudos_antigos[nome_antigo]
                estudo.nome = nome
                estudo.condicao = condicao
                estudo.descricao = descricao
                estudos_renomeados.append(estudo)
                estudos_demo.append(estudo)
                continue
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
        nomes_voluntarios = {}
        rng_nomes = random.Random(options["seed"] + 70_000)
        nomes_usados = set()
        for numero in range(1, TOTAL_VOLUNTARIOS + 1):
            nome = nome_voluntario(numero, rng_nomes)
            while nome in nomes_usados:
                nome = nome_voluntario(numero, rng_nomes)
            nomes_usados.add(nome)
            nomes_voluntarios[numero] = nome

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
        voluntarios_atualizados = 0
        novos_criterios = 0
        novas_participacoes = 0

        with transaction.atomic():
            if estudos_renomeados:
                Estudo.objects.bulk_update(estudos_renomeados, ["nome", "condicao", "descricao"], batch_size=250)
            if estudos_atualizados:
                Estudo.objects.bulk_update(estudos_atualizados, ["condicao", "descricao"], batch_size=250)
            if novos_estudos:
                Estudo.objects.bulk_create(novos_estudos, batch_size=250)
                estudos_demo.extend(novos_estudos)
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
            voluntarios_para_atualizar = []
            for numero in range(1, TOTAL_VOLUNTARIOS + 1):
                identificador = identificador_por_numero[numero]
                voluntario_existente = existentes_voluntarios.get(identificador)
                if voluntario_existente:
                    # Só atualiza nomes de registros deste carregador, nunca os cadastros existentes de usuários.
                    email_existente = voluntario_existente.obter_email()
                    nome = nomes_voluntarios[numero]
                    if email_existente.startswith("demo-voluntario-") and voluntario_existente.obter_nome() != nome:
                        voluntario_existente.nome_cifrado = cifrar(nome)
                        voluntarios_para_atualizar.append(voluntario_existente)
                    continue
                cpf = cpf_por_numero[numero]
                nome = nomes_voluntarios[numero]
                email = f"demo-voluntario-{numero:05d}@example.invalid"
                autorizou = rng.choice((True, False))
                criado_em = agora - timedelta(days=rng.randint(0, 364), hours=rng.randint(0, 23))
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
            for lote in lotes(voluntarios_para_atualizar, 250):
                Voluntario.objects.bulk_update(lote, ["nome_cifrado"], batch_size=250)
            voluntarios_atualizados = len(voluntarios_para_atualizar)

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
        self.stdout.write(
            f"Pesquisas renomeadas: {len(estudos_renomeados)}; descrições atualizadas: {len(estudos_atualizados)}. "
            f"Nomes de voluntários atualizados: {voluntarios_atualizados}. "
            "A base permanece sintética; e-mails de exemplo não recebem mensagens."
        )
