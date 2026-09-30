import time

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL_NAME = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"

print(f"Baixando/Carregando {MODEL_NAME}...")
t0 = time.time()
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
model.eval()
print(f"Modelo carregado em {time.time() - t0:.2f}s!")

cases = [
    {
        "name": "Caso Barcelona (Ausência de confirmação não é contradição)",
        "premise": "A atriz Fernanda Serrano participou de um filme rodado em Barcelona em 1996.",
        "hypothesis": "Hoje em Barcelona, Bloco Amantes Latinos aquecendo os tambores.",
    },
    {
        "name": "Caso Benedita (Suporte explícito em debate)",
        "premise": (
            "Benedita da Silva, Carlos Jordy e outros candidatos ao Senado pelo Rio de "
            "Janeiro participaram dos debates promovidos pelo g1."
        ),
        "hypothesis": "Benedita da Silva concorre a senadora pelo Rio de Janeiro.",
    },
    {
        "name": "Caso Desmentido Real (Contradição explícita)",
        "premise": (
            "É falso que Benedita da Silva concorra ao Senado pelo Rio. Ela já confirmou "
            "que não disputará nenhum cargo em 2026."
        ),
        "hypothesis": "Benedita da Silva concorre a senadora pelo Rio de Janeiro.",
    },
    {
        "name": "Caso Flávio Dino (Confirmação judicial)",
        "premise": (
            "O ministro do STF Flávio Dino derrubou neste domingo a decisão liminar do ministro "
            "André Mendonça que havia censurado postagens de Antônio Tabet."
        ),
        "hypothesis": (
            "Ministro Flávio Dino suspendeu a decisão de André Mendonça que censurou a "
            "postagem de Antônio Tabet."
        ),
    },
]

print("\nExecutando inferências NLI na CPU...")
for case in cases:
    t_start = time.time()
    inputs = tokenizer(
        case["premise"],
        case["hypothesis"],
        truncation=True,
        max_length=512,
        return_tensors="pt",
    )
    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=1)[0].tolist()

    id2label = model.config.id2label
    results = {id2label[i].lower(): probs[i] for i in range(len(probs))}
    latency = (time.time() - t_start) * 1000

    print(f"\n[{case['name']}] ({latency:.1f}ms):")
    print(f"  Premissa:   {case['premise'][:80]!r}")
    print(f"  Hipótese:   {case['hypothesis'][:80]!r}")
    print(f"  Resultados: {results}")
