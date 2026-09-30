from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.domain.entities import Evidence, Post, VerdictLabel
from app.services.crc import CRCCalibration
from app.services.jev_verification import JevVerificationService, _explicit_candidate_support


class StaticCalibrations:
    def __init__(self, calibration: CRCCalibration | None) -> None:
        self.calibration = calibration

    def get_latest(self, model: str) -> CRCCalibration | None:
        return self.calibration


def build_service(calibration: CRCCalibration | None, **settings) -> JevVerificationService:
    return JevVerificationService(
        classifier=None,
        sources=[],
        calibration_repo=StaticCalibrations(calibration),
        settings=Settings(_env_file=None, **settings),
    )


def calibration(lambda_hat: float) -> CRCCalibration:
    return CRCCalibration(
        lambda_hat=lambda_hat, alpha=0.05, n=40, model="jev", created_at=datetime.now(UTC)
    )


def test_abstains_without_calibration_by_default():
    label, confidence, rationale = build_service(None)._apply_calibration(
        VerdictLabel.FALSE, 0.95, 2
    )
    assert label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert confidence == 0.0
    assert "não há calibração" in rationale


def test_allow_uncalibrated_keeps_raw_verdict_and_says_so():
    service = build_service(None, jev_allow_uncalibrated=True)
    label, confidence, rationale = service._apply_calibration(VerdictLabel.FALSE, 0.95, 2)
    assert label == VerdictLabel.FALSE
    assert confidence == 0.95
    assert "JEV_ALLOW_UNCALIBRATED" in rationale


@pytest.mark.parametrize("allow_uncalibrated", [False, True])
def test_existing_calibration_still_gates_low_confidence(allow_uncalibrated):
    service = build_service(calibration(0.9), jev_allow_uncalibrated=allow_uncalibrated)
    label, _, rationale = service._apply_calibration(VerdictLabel.MISLEADING, 0.85, 1)
    assert label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert "lambda_hat" in rationale


class ScriptedClassifier:
    """Relevância pelo título da evidência; veredito fixo. Registra os prompts."""

    def __init__(self, relevance_by_title: dict[str, float]) -> None:
        self.relevance_by_title = relevance_by_title
        self.questions: list[str] = []

    async def classify(self, question: str, options: list[str]) -> dict[str, float]:
        self.questions.append(question)
        if options == ["relevante", "irrelevante"]:
            score = next(v for title, v in self.relevance_by_title.items() if title in question)
            return {"relevante": score, "irrelevante": 1 - score}
        # Veredito: confirmam=0.1, desmentem=0.7, distorcem=0.2 (ordem de _LABEL_BY_OPTION).
        return dict(zip(options, [0.1, 0.7, 0.2], strict=True))

    async def count_tokens(self, texts: list[str]) -> list[int]:
        # Matéria completa "pesa" 3000 tokens; o resto, 10.
        return [3000 if "matéria completa" in text else 10 for text in texts]


def evidence(url: str, title: str) -> Evidence:
    return Evidence(source="test", url=url, title=title, snippet="")


def test_explicit_candidate_support_blocks_benedita_false_positive():
    claim = (
        "É com muito orgulho que recebo o apoio da deputada federal Benedita da Silva, "
        "que nesta eleição concorre a senadora pelo Rio de Janeiro."
    )
    source = Evidence(
        "g1",
        "https://g1.example/eleicoes",
        "Debate de candidatos ao Senado pelo Rio",
        "Benedita da Silva, Carlos Jordy e outros candidatos ao Senado pelo Rio "
        "participaram dos debates no g1.",
    )

    assert _explicit_candidate_support(claim, [source]) == source.url


def test_candidate_guard_does_not_treat_a_denial_as_support():
    claim = "Benedita da Silva concorre a senadora pelo Rio de Janeiro."
    source = Evidence(
        "test",
        "https://example.org/negacao",
        "Checagem de candidatura",
        "É falso que Benedita da Silva seja candidata ao Senado pelo Rio.",
    )

    assert _explicit_candidate_support(claim, [source]) is None


async def test_jev_abstains_when_its_false_verdict_conflicts_with_explicit_support(monkeypatch):
    claim = "Benedita da Silva concorre a senadora pelo Rio de Janeiro."
    source = Evidence(
        "g1",
        "https://g1.example/eleicoes",
        "Debate de candidatos ao Senado pelo Rio",
        "Benedita da Silva e outros candidatos ao Senado pelo Rio participaram.",
    )
    service = build_service(calibration(0.5))
    monkeypatch.setattr(service, "_search", AsyncMock(return_value=([source], {}, claim)))
    monkeypatch.setattr(service, "_filter_relevant", AsyncMock(return_value=([source], [])))
    monkeypatch.setattr(
        service,
        "_classify_verdict",
        AsyncMock(return_value=(VerdictLabel.FALSE, 0.999, {"desmentem a alegação": 0.999})),
    )

    verdict = await service._verify_claim(claim, {}, prefix="jev.c01", post_date=date(2026, 9, 28))

    assert verdict.label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert verdict.confidence == 0.0
    assert "fonte relevante apresenta" in verdict.rationale


async def test_filter_relevant_shortlists_by_word_overlap_and_sorts_by_margin():
    claim = "Dino suspendeu decisão de Mendonça sobre postagem de Tabet"
    unrelated = [f"futebol campeonato rodada {i}" for i in range(10)]
    evidences = [evidence(f"https://x/{i}", title) for i, title in enumerate(unrelated)] + [
        evidence("https://a", "Dino suspende decisão de Mendonça"),
        evidence("https://b", "Dino suspende decisão de Mendonça sobre postagem de Tabet"),
    ]
    scores = {title: 0.9 for title in unrelated} | {
        "Dino suspende decisão de Mendonça sobre": 0.95,
        "Dino suspende decisão de Mendonça": 0.8,
    }
    classifier = ScriptedClassifier(scores)
    service = build_service(None)
    service.classifier = classifier

    relevant, log = await service._filter_relevant(claim, evidences)

    # As fontes sem duas âncoras factuais são vetadas antes de consumir Jev.
    assert len(classifier.questions) == 2
    assert len(log) == len(evidences)
    assert {"https://a", "https://b"} <= {entry["url"] for entry in log}
    assert relevant[0].url == "https://b"
    margins = [entry["relevante"] - entry["irrelevante"] for entry in log if "reason" not in entry]
    assert len(relevant) == sum(margin >= 0.15 for margin in margins)


async def test_filter_relevant_rejects_location_only_match_before_jev():
    claim = "Hoje em Barcelona, Bloco Amantes Latinos aquecendo os tambores"
    evidences = [
        evidence("https://fernanda", "Fernanda Serrano em Barcelona"),
        evidence("https://factory", "Fábrica de Barcelona volta à produção"),
        evidence("https://event", "Bloco Amantes Latinos faz evento em Barcelona"),
    ]
    classifier = ScriptedClassifier({"Bloco Amantes Latinos faz evento": 0.9})
    service = build_service(None)
    service.classifier = classifier

    relevant, log = await service._filter_relevant(claim, evidences)

    assert [item.url for item in relevant] == ["https://event"]
    assert len(classifier.questions) == 1
    rejected = {entry["url"] for entry in log if entry.get("reason")}
    assert rejected == {"https://fernanda", "https://factory"}


def test_candidate_sentences_ignores_hashtag_only_lines():
    from app.services.jev_verification import _candidate_sentences

    assert _candidate_sentences("#LulaNoPrimeiroTurno\nA eleição será amanhã.") == [
        "A eleição será amanhã."
    ]


def test_candidate_sentences_ignores_campaign_labels():
    from app.services.jev_verification import _candidate_sentences

    assert _candidate_sentences(
        "Núcleo PT Barcelona\nComitê Lula Presidente - Barcelona\nHoje houve um ato em Barcelona."
    ) == ["Hoje houve um ato em Barcelona."]


async def test_verdict_packs_full_articles_until_the_context_limit(monkeypatch):
    from app.services import jev_verification

    async def article(url: str):
        return f"matéria completa de {url}"

    monkeypatch.setattr(jev_verification, "_fetch_article_text", article)
    classifier = ScriptedClassifier({})
    service = build_service(None, jev_n_ctx=4096)
    service.classifier = classifier
    relevant = [
        Evidence(source="t", url=f"https://e{i}", title=f"Fonte {i}", snippet=f"trecho {i}")
        for i in range(7)
    ]

    label, confidence, _ = await service._classify_verdict("alegação", relevant)

    prompt = classifier.questions[-1]
    assert label == VerdictLabel.FALSE
    assert confidence == 0.7
    # 4096 de contexto: só a primeira matéria cabe inteira (3000); as outras
    # entram com o trecho da busca, até o teto de 5 evidências.
    assert "matéria completa de https://e0" in prompt
    assert "matéria completa de https://e1" not in prompt
    assert all(f"trecho {i}" in prompt for i in range(1, 5))
    assert "trecho 5" not in prompt


class EmptySource:
    name = "empty"

    def __init__(self) -> None:
        self.queries: list[str] = []

    async def search(self, query: str, *, limit: int = 5):
        self.queries.append(query)
        return []


class ContextClassifier:
    def __init__(self) -> None:
        self.questions: list[str] = []

    async def classify(self, question: str, options: list[str]) -> dict[str, float]:
        self.questions.append(question)
        if options == ["factual", "opiniao"]:
            factual = "221 bi em depósitos" in question
            return {"factual": 0.9 if factual else 0.1, "opiniao": 0.1 if factual else 0.9}
        return dict.fromkeys(options, 1 / len(options))

    async def count_tokens(self, texts: list[str]) -> list[int]:
        return [10 for _ in texts]


async def test_jev_considers_limited_thread_context_as_candidate_claim():
    classifier = ContextClassifier()
    service = build_service(None)
    service.classifier = classifier
    service.sources = [EmptySource()]
    post = Post(
        uri="at://did:plc:a/app.bsky.feed.post/1",
        cid="c",
        author_did="did:plc:a",
        text="Acho esse assunto estranho.",
        created_at=datetime.now(UTC),
    )

    verdict = await service.verify(
        post,
        parent_text="continuação do autor: Os valores chegaram a 221 bi em depósitos.",
    )

    assert verdict.label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert "221 bi em depósitos" in verdict.claim
    assert any("221 bi em depósitos" in question for question in classifier.questions)


async def test_jev_searches_with_post_date_for_temporal_claim():
    source = EmptySource()
    service = build_service(None)
    service.sources = [source]

    _, _, query = await service._search(
        "Hoje houve um ato em Barcelona", post_date=date(2026, 9, 27)
    )

    assert query.endswith("27/09/2026")
    assert source.queries == [query]


def test_candidate_sentences_rejects_questions_and_idioms():
    from app.services.jev_verification import _candidate_sentences

    text = (
        "BOMBÁSTICO\n\n"
        "VOCÊS LEMBRAM DAS FESTINHAS ÍNTIMAS DO FLÁVIO BOLSONARO?\n\n"
        "Corre. A casa começou a cair. Saiu hoje no PlatôBR: Ex-sócio da loja de chocolate, "
        "prints, áudios, notas fiscais, whatsApp pedindo “festinha igual à do Grand Hyatt”.\n\n"
        "Foto da varanda, recado na"
    )
    candidates = _candidate_sentences(text)
    assert not any("VOCÊS LEMBRAM" in c for c in candidates)
    assert not any("A casa começou a cair" in c for c in candidates)
    assert not any("recado na" in c for c in candidates)
    assert any("Saiu hoje no PlatôBR" in c for c in candidates)


def test_candidate_sentences_extracts_metrics_and_entities():
    from app.services.jev_verification import _candidate_sentences

    text = (
        "Rolex de R$ 305 mil.\n"
        "Academia de R$ 90 mil.\n"
        "Casa de R$ 5,9 milhões.\n"
        "Caixa dos amigos.\n"
        "conversa com Kassio pra empurrar processo."
    )
    candidates = _candidate_sentences(text)
    assert "Rolex de R$ 305 mil." in candidates
    assert "Academia de R$ 90 mil." in candidates
    assert "Casa de R$ 5,9 milhões." in candidates
    assert "conversa com Kassio pra empurrar processo." in candidates
    assert "Caixa dos amigos." not in candidates


def test_has_direct_anchor_overlap_rejects_literal_metaphor_and_weather():
    from app.services.jev_verification import _has_direct_anchor_overlap

    claim = "A casa começou a cair."
    ev_pelotas = Evidence(
        source="tavily",
        url="https://www.instagram.com/reel/Dd3mlMZARkR",
        title="Caroline Mendes, de Pelotas (RS ...",
        snippet=(
            "Segundo Caroline, a força do vento provocou danos na estrutura "
            "da residência e parte do telhado começou a cair."
        ),
    )
    assert not _has_direct_anchor_overlap(claim, ev_pelotas, context_entity="Flávio Bolsonaro")


async def test_search_contextualizes_with_entity():
    source = EmptySource()
    service = build_service(None)
    service.sources = [source]

    _, _, query = await service._search("Rolex de R$ 305 mil.", context_entity="Flávio Bolsonaro")

    assert query == "Rolex de R$ 305 mil. Flávio Bolsonaro"
    assert source.queries == [query]


def test_candidate_sentences_strips_trailing_connectors_and_retains_claims():
    from app.services.jev_verification import _candidate_sentences

    post_695 = (
        "Hoje é um bom dia para lembrar que em 2018 o Luciano Huck lançou um app "
        "pra te ajudar a escolher candidato que só indicava candidato de direita e ele "
        "realmente achou que ninguém ia perceber e"
    )
    candidates = _candidate_sentences(post_695)
    assert len(candidates) == 1
    assert candidates[0].startswith("Hoje é um bom dia para lembrar que em 2018 o Luciano Huck")
    assert not candidates[0].endswith(" e")


def test_extract_primary_entities_handles_all_caps_names_and_prioritizes_multiword():
    from app.services.jev_verification import _extract_primary_entities

    text = "BOMBÁSTICO VOCÊS LEMBRAM DAS FESTINHAS ÍNTIMAS DO FLÁVIO BOLSONARO? Grand Hyatt"
    entities = _extract_primary_entities(text)
    assert entities[0] == "Flávio Bolsonaro"
    assert "Grand Hyatt" in entities
    assert "DAS" not in entities
    assert "DO" not in entities


def test_extract_primary_entities_does_not_extract_all_caps_headlines_as_person():
    from app.services.jev_verification import _extract_primary_entities

    headline = "🚨 STF FORMOU MAIORIA PARA GARANTIR ACESSO À INFORMAÇÃO NAS ELEIÇÕES!"
    entities = _extract_primary_entities(headline)
    assert entities == ["STF"]


def test_has_direct_anchor_overlap_rejects_social_media_and_same_origin():
    from app.services.jev_verification import _has_direct_anchor_overlap

    claim = "STF formou maioria para garantir acesso à informação nas eleições"
    ev_insta = Evidence(
        source="tavily",
        url="https://www.instagram.com/p/DAilxyz/",
        title="STF formou maioria para garantir acesso",
        snippet="decisão do STF garante acesso aos sites eleitorais",
    )
    # 1. Instagram / social media blocked
    assert not _has_direct_anchor_overlap(claim, ev_insta)

    # 2. Same-origin evidence blocked (Sleeping Giants checking Sleeping Giants)
    ev_same_origin = Evidence(
        source="web_search",
        url="https://sleepinggiantsbrasil.org/post/stf-maioria",
        title="Sleeping Giants Brasil: STF formou maioria para garantir acesso",
        snippet="decisão do STF garante acesso",
    )
    assert not _has_direct_anchor_overlap(
        claim, ev_same_origin, author_handle="sleepinggiantsbr.bsky.social"
    )


def test_candidate_sentences_ignores_dialogue_questions_with_dashes():
    from app.services.jev_verification import _candidate_sentences

    post_695 = (
        "- como foi a eleição de 2026\n"
        "- bom um dos detalhes foi a hora que o Luciano Huck lançou um app "
        "pra te ajudar a escolher candidato que só indicava candidato de direita e ele "
        "realmente achou que ninguém ia perceber e"
    )
    candidates = _candidate_sentences(post_695)
    assert len(candidates) == 1
    assert "Luciano Huck" in candidates[0]


def test_has_direct_anchor_overlap_rejects_politician_only_match_when_context_entity_present():
    from app.services.jev_verification import _has_direct_anchor_overlap

    claim = "Flávio Bolsonaro assumiu a defesa do PM e julgamento até hoje não aconteceu."
    context = "Ana Clara Gomes Machado"

    # Evidência que fala só da eleição de Flávio Bolsonaro (sem Ana Clara nem defesa/julgamento)
    ev_generic = Evidence(
        source="lupa",
        url="https://agencialupa.org/eleicoes-flavio",
        title="É falso que Flávio Bolsonaro não disputará as eleições",
        snippet="Tribunal Superior Eleitoral manteve registro de Flávio Bolsonaro",
    )
    assert not _has_direct_anchor_overlap(claim, ev_generic, context_entity=context)

    # Evidência que traz o caso específico (mencionando o júri do PM ou defesa)
    ev_case = Evidence(
        source="atarde",
        url="https://atarde.com.br/flavio-juri-pm",
        title="Entenda como Flávio Bolsonaro travou júri de PM acusado de matar menina",
        snippet="recurso assinado pela defesa no processo de homicídio que aguarda julgamento",
    )
    assert _has_direct_anchor_overlap(claim, ev_case, context_entity=context)


def test_candidate_sentences_ignores_campaign_slogans_and_countdowns():
    from app.services.jev_verification import _candidate_sentences

    post_cheerleading = (
        "FALTAM 7 DIAS PARA LULA ELEITO NO PRIMEIRO TURNO\n\n"
        "LULA ELEITO NO PRIMEIRO TURNO\n\n"
        "LULA PRESIDENTE\n\n"
        "#LULA2026\n\n"
        "1️⃣3️⃣✅️"
    )
    candidates = _candidate_sentences(post_cheerleading)
    assert candidates == []


@pytest.mark.asyncio
async def test_reply_post_does_not_inherit_claims_from_parent_post():
    from app.services.jev_verification import JevVerificationService

    class RecordingClassifier:
        def __init__(self):
            self.questions = []

        async def classify(self, question: str, options: list[str]) -> dict[str, float]:
            self.questions.append(question)
            return {"factual": 0.1, "opiniao": 0.9}

        async def count_tokens(self, texts: list[str]) -> list[int]:
            return [10] * len(texts)

        async def predict_nli_batch(self, pairs):
            return [{"entailment": 0.0, "neutral": 1.0, "contradiction": 0.0}] * len(pairs)

    classifier = RecordingClassifier()
    service = JevVerificationService(
        classifier=classifier,
        sources=[],
        calibration_repo=StaticCalibrations(None),
        settings=Settings(_env_file=None),
    )

    adila_reply = Post(
        uri="at://did:plc:adila/app.bsky.feed.post/123",
        cid="cid1",
        author_did="did:plc:adila",
        author_handle="adila.bsky.social",
        text=(
            "Bora Haddad, SP merece um governo como você! 🤩\n"
            "O bandido TarCÍNICO, fugiu das perguntas o tempo todo!"
        ),
        created_at=datetime.now(UTC),
    )
    zem_parent_text = (
        "post anterior: SP PODE E MERECE MAIS \n\n"
        "No debate da Globo, Haddad jantou o Tarcínico ao falar a verdade "
        "sobre dados da violência em SP:\n\n"
        "Feminicídio em alta, recorde de crimes de natureza racial, \n"
        "ódio contra minorias, recorde de roubos de celulares e o PCC em alta\n\n"
        "BORA HADDAD 13"
    )

    verdict = await service.verify(adila_reply, parent_text=zem_parent_text)

    # 1. Deve se abster de publicar intervenção contra o comentário
    assert verdict.label == VerdictLabel.INSUFFICIENT_EVIDENCE
    assert verdict.confidence == 0.0

    # 2. As frases factuais do post anterior (Zem) NÃO devem ser investigadas para a Adila
    assert not any("Feminicídio em alta" in q for q in classifier.questions)
    assert not any("jantou o Tarcínico" in q for q in classifier.questions)


def test_has_direct_anchor_overlap_rejects_third_party_denial():
    from app.services.jev_verification import _has_direct_anchor_overlap

    ev = Evidence(
        source="oglobo",
        url="https://oglobo.globo.com/politica/noticia/2024/05/20/flavio-bolsonaro-vorcaro.ghtml",
        title="Flávio diz que Bolsonaro nunca se encontrou com Vorcaro, do Banco Master",
        snippet="Senador afirmou que ex-presidente jamais esteve com o banqueiro.",
    )

    # 1. Alegação sobre o emissor da fala (Flávio) NÃO pode ser contradita por negação sobre o pai
    claim_flavio = (
        "Flávio se encontrou com Vorcaro quando o cara já estava de tornozeleira eletrônica"
    )
    assert not _has_direct_anchor_overlap(claim_flavio, ev)

    # 2. Funciona mesmo com sobrenome composto no post ("Flávio Bolsonaro")
    claim_flavio_full = (
        "Flávio Bolsonaro se encontrou com Vorcaro quando o cara já estava de tornozeleira"
    )
    assert not _has_direct_anchor_overlap(claim_flavio_full, ev)

    # 3. Mas se a alegação for diretamente sobre o sujeito da negação (Jair Bolsonaro), aceita
    claim_bolsonaro = "Jair Bolsonaro se encontrou com Vorcaro em jantar secreto"
    assert _has_direct_anchor_overlap(claim_bolsonaro, ev)


def test_candidate_sentences_ignores_anaphoric_relative_clauses_and_blind_items():
    from app.services.jev_verification import _candidate_sentences

    post_cyrus = (
        "13 candidatos à Presidência da República\n"
        "Só um recebeu grana do Vorcaro,\n"
        "o mesmo que voou no jatinho do Vorcaro,\n"
        "o mesmo que marcou jantar com o Vorcaro\n"
        "e o mesmo que se encontrou com Vorcaro, quando o cara já estava de tornozeleira "
        "eletrônica, pra pedir mais grana\n"
        "Em 4/10 tá fácil escolher"
    )
    candidates = _candidate_sentences(post_cyrus)
    assert candidates == []
