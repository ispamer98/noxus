"""Persiste las migraciones idempotentes del almacén de nodos.

La migración real vive en ``domains.nodes.store._apply_defaults`` para que
tanto las lecturas como las escrituras vean siempre el mismo esquema. Este
script solo fuerza una escritura atómica del resultado y respeta ``NODOS_FILE``.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from noxuscmmd.domains.nodes import store


def main() -> None:
    store.apply_migrations()
    data = store.read_all()
    print(f"sensores: {len(data['sensors'])}")
    print(f"cámaras: {len(data['cameras'])}")
    print("Migración aplicada.")


if __name__ == "__main__":
    main()
