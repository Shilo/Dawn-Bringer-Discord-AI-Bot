"""Shared state for RAG chain access across modules."""

rag_chain = None

def get_rag_chain():
    return rag_chain

def set_rag_chain(value):
    global rag_chain
    rag_chain = value

