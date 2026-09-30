import pytest

from app.models.classifiers.jev import JevClassifier, _validate_options


def test_validate_options():
    _validate_options(["sim", "não"])
    with pytest.raises(ValueError, match="aceita entre 2 e"):
        _validate_options(["sim"])
    with pytest.raises(ValueError, match="não podem se repetir"):
        _validate_options(["sim", "sim"])


@pytest.mark.asyncio
async def test_jev_classifier_e2e_nli():
    classifier = JevClassifier()

    # 1. Contagem de tokens
    counts = await classifier.count_tokens(["Olá mundo", "Teste de contagem"])
    assert len(counts) == 2
    assert all(c > 0 for c in counts)

    # 2. Inferência NLI direta
    nli = await classifier.predict_nli(
        premise="Benedita da Silva participa do debate de candidatos ao Senado pelo Rio",
        hypothesis="Benedita da Silva concorre ao Senado",
    )
    assert "entailment" in nli
    assert "neutral" in nli
    assert "contradiction" in nli
    assert nli["entailment"] > 0.50

    # 3. Classificação factual vs opinião
    factual_res = await classifier.classify(
        'Frase: "Os depósitos atingiram 221 bilhões de reais."\nEssa frase é factual ou opinião?',
        ["factual", "opiniao"],
    )
    assert factual_res["factual"] > factual_res["opiniao"]

    opinion_res = await classifier.classify(
        'Frase: "Acho essa medida horrível e inaceitável."\nEssa frase é factual ou opinião?',
        ["factual", "opiniao"],
    )
    assert opinion_res["opiniao"] > opinion_res["factual"]

    # 4. Filtragem de relevância
    rel_res = await classifier.classify(
        'Alegação a verificar: "Benedita concorre ao Senado"\n'
        'Trecho de fonte: "G1 realiza debate com candidatos ao Senado no Rio incluindo Benedita"',
        ["relevante", "irrelevante"],
    )
    assert rel_res["relevante"] > rel_res["irrelevante"]

    irrel_res = await classifier.classify(
        'Alegação a verificar: "Carnaval em Barcelona"\n'
        'Trecho de fonte: "Fernanda Serrano participou de filme em Barcelona em 1996"',
        ["relevante", "irrelevante"],
    )
    assert irrel_res["irrelevante"] > irrel_res["relevante"]

    # 5. Veredito
    verdict_res = await classifier.classify(
        'Alegação: "Dino suspendeu a decisão de Mendonça"\n'
        "Evidências encontradas:\n- Flávio Dino derrubou a decisão liminar de André Mendonça\n"
        "O que as evidências acima dizem sobre a alegação?",
        [
            "confirmam a alegação",
            "desmentem a alegação",
            "confirmam o fato, mas desmentem a conclusão ou o exagero da alegação",
        ],
    )
    assert verdict_res["confirmam a alegação"] > verdict_res["desmentem a alegação"]
