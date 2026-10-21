"""Shared helpers for the test suite: everything runs offline on tiny fixtures.

The fixtures are CodeGuard's own clean-room utilities (``data/negatives``), which
keeps the tests honest - no third-party source ends up inside the repository.
"""

import os
import shutil
import tempfile

from codeguard.index import DocRecord, FingerprintIndex, Params
from codeguard.normalize import tokenize_source

import hashlib

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEGATIVE_DIR = os.path.join(PKG_ROOT, "src", "codeguard", "data", "negatives")


def negative_names():
    return sorted(n for n in os.listdir(NEGATIVE_DIR) if n.endswith(".py"))


def read_negative(name):
    with open(os.path.join(NEGATIVE_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def make_corpus(names, dest_root):
    """Copy fixtures into a mini corpus tree and return (docs, texts)."""
    docs, texts = [], []
    for doc_id, name in enumerate(names):
        text = read_negative(name)
        folder = "fixture-0.1.0"
        target = os.path.join(dest_root, folder, name)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copyfile(os.path.join(NEGATIVE_DIR, name), target)
        docs.append(DocRecord(doc_id, "fixture", "0.1.0", "%s/%s" % (folder, name),
                              "Apache-2.0", "self-authored", "python",
                              text.count("\n") + 1, len(tokenize_source(text)),
                              hashlib.sha256(text.encode()).hexdigest(), len(text)))
        texts.append(text)
    return docs, texts


def build_index(corpus_root, docs, texts, **param_kw):
    index = FingerprintIndex(Params(**param_kw))
    index.corpus_root = corpus_root
    for doc, text in zip(docs, texts):
        index.add_document(doc, text)
    return index.finalize()


def tempdir():
    return tempfile.mkdtemp(prefix="codeguard-test-")
