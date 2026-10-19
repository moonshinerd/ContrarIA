"""Cancela o rótulo pendente de um post do Poder360 (intervenção indevida).

O coletor de alegações checadas casou o post oficial do Poder360 sobre a pesquisa
PoderData/Aya com uma checagem de outra pesquisa; o rótulo ficou na caixa de saída
sem ter sido entregue (Ozone fora do ar) e seria aplicado quando o Ozone voltasse.

Revision ID: 0004_cancela_rotulo_poder360
Revises: 0003_create_label_events
Create Date: 2026-10-19
"""

from alembic import op

revision = "0004_cancela_rotulo_poder360"
down_revision = "0003_create_label_events"
branch_labels = None
depends_on = None

_POST_URI = "at://did:plc:2sz7lzabaabo52nd2p2h722t/app.bsky.feed.post/3my7xbqvtf22v"


def upgrade() -> None:
    op.execute(
        f"UPDATE label_events SET status = 'failed', "  # noqa: S608
        f"last_error = 'Cancelado: autor é veículo de imprensa (intervenção indevida)' "
        f"WHERE status = 'pending' AND action = 'create' AND subject_uri = '{_POST_URI}'"
    )


def downgrade() -> None:
    # Não reativa o rótulo cancelado: seria reaplicar uma marcação indevida.
    pass
