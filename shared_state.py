"""Shared state for RAG chain access across modules."""

rag_chain = None
client_ready = False
gift_code_channel = None
cached_gift_codes = None  # Cached gift codes for web interface

def get_rag_chain():
    return rag_chain

def set_rag_chain(value):
    global rag_chain
    rag_chain = value

def get_client_ready():
    return client_ready

def set_client_ready(value):
    global client_ready
    client_ready = value

def get_gift_code_channel():
    return gift_code_channel

def set_gift_code_channel(value):
    global gift_code_channel
    gift_code_channel = value

def get_cached_gift_codes():
    return cached_gift_codes

def set_cached_gift_codes(value):
    global cached_gift_codes
    cached_gift_codes = value

