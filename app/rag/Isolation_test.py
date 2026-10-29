"""
CRITICAL isolation test for Weaviate multi-tenancy.

Run this AFTER the stack is up, from inside the api container or any environment
that can reach Weaviate, to PROVE that one user cannot see another user's docs.

This is the single most important test of the Chroma->Weaviate migration. A
multi-tenant platform that leaks documents across users is a serious security
failure. Do not trust the migration until this passes.

Usage (from the host, with the stack running):
    docker compose -f docker/docker-compose.yml exec api python -m app.rag.isolation_test

Or copy this file to app/rag/isolation_test.py and run as a module.
"""
import uuid

from langchain_core.documents import Document

from app.rag.collections import (
    add_documents_for,
    count_for,
    delete_user_collection,
    search_for,
)


def main() -> None:
    # Two distinct fake users.
    alice = uuid.uuid4()
    bob = uuid.uuid4()
    print(f"Alice = {alice}")
    print(f"Bob   = {bob}")

    # Clean slate.
    delete_user_collection(alice)
    delete_user_collection(bob)

    # Alice gets a document about cats. Bob gets one about spacecraft.
    add_documents_for(alice, [
        Document(page_content="Alice's secret: the cat's name is Mittens.",
                 metadata={"source_file": "alice.txt", "page": 0}),
    ])
    add_documents_for(bob, [
        Document(page_content="Bob's secret: the spacecraft launches at dawn.",
                 metadata={"source_file": "bob.txt", "page": 0}),
    ])

    print(f"\nAlice chunk count: {count_for(alice)} (expect 1)")
    print(f"Bob chunk count:   {count_for(bob)} (expect 1)")

    # Alice searches for Bob's secret. Must NOT find the spacecraft doc.
    alice_results = search_for(alice, "spacecraft launch dawn", k=5)
    bob_results = search_for(bob, "cat named Mittens", k=5)

    alice_texts = " ".join(d.page_content for d, _ in alice_results)
    bob_texts = " ".join(d.page_content for d, _ in bob_results)

    print("\n--- Alice's search results (querying for Bob's content) ---")
    for d, s in alice_results:
        print(f"  [{s:.3f}] {d.page_content}")
    print("\n--- Bob's search results (querying for Alice's content) ---")
    for d, s in bob_results:
        print(f"  [{s:.3f}] {d.page_content}")

    # The critical assertions.
    leaked = False
    if "spacecraft" in alice_texts.lower():
        print("\n!!! FAIL: Alice can see Bob's spacecraft document. ISOLATION BROKEN.")
        leaked = True
    if "mittens" in bob_texts.lower():
        print("\n!!! FAIL: Bob can see Alice's cat document. ISOLATION BROKEN.")
        leaked = True

    if not leaked:
        print("\n=== PASS: tenants are isolated. Neither user can see the other's docs. ===")

    # Cleanup.
    delete_user_collection(alice)
    delete_user_collection(bob)
    print("\n(cleaned up test tenants)")

    if leaked:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
