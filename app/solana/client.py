"""
Minimal Solana memo transaction client for devnet/mainnet.
Requires SOLANA_PRIVATE_KEY (base58) and SOLANA_ENABLED=true.
If solders/solana packages missing or key empty — raises clear error.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def send_checkpoint_memo(memo_text: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.solana_private_key:
        return {"signature": None, "error": "SOLANA_PRIVATE_KEY not set"}

    try:
        from solders.keypair import Keypair
        from solders.pubkey import Pubkey
        from solders.system_program import TransferParams, transfer
        from solders.transaction import Transaction
        from solders.message import Message
        from solders.hash import Hash
        from solana.rpc.api import Client
        from solana.rpc.commitment import Confirmed
    except ImportError as e:
        return {"signature": None, "error": f"solana deps missing: {e}"}

    try:
        # Key can be base58 secret or JSON byte array string
        raw = settings.solana_private_key.strip()
        if raw.startswith("["):
            import json

            kp = Keypair.from_bytes(bytes(json.loads(raw)))
        else:
            kp = Keypair.from_base58_string(raw)

        client = Client(settings.solana_rpc_url)
        recent = client.get_latest_blockhash(commitment=Confirmed)
        blockhash = recent.value.blockhash

        # Memo program id
        memo_program = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")

        # Self-transfer 0 + memo instruction via raw compile is complex;
        # use solders Instruction for memo
        from solders.instruction import Instruction, AccountMeta

        memo_ix = Instruction(
            program_id=memo_program,
            data=memo_text.encode("utf-8"),
            accounts=[AccountMeta(pubkey=kp.pubkey(), is_signer=True, is_writable=False)],
        )
        # Tiny self-transfer to have a fee-paying tx
        tx_ix = transfer(
            TransferParams(
                from_pubkey=kp.pubkey(),
                to_pubkey=kp.pubkey(),
                lamports=0,
            )
        )
        msg = Message.new_with_blockhash([tx_ix, memo_ix], kp.pubkey(), blockhash)
        tx = Transaction.new_unsigned(msg)
        tx.sign([kp], blockhash)

        resp = client.send_transaction(tx)
        sig = str(resp.value)
        # Optional confirm
        try:
            conf = client.confirm_transaction(resp.value, commitment=Confirmed)
            slot = None
            if conf and conf.value:
                slot = None  # slot available via get_transaction if needed
        except Exception:
            pass

        return {"signature": sig, "slot": slot, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.exception("send_checkpoint_memo failed")
        return {"signature": None, "error": str(exc)}
