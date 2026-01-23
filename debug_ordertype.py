
try:
    from py_clob_client.client import ClobClient
    import inspect
    
    print("create_and_post_order signature:", inspect.signature(ClobClient.create_and_post_order))
    print("post_order signature:", inspect.signature(ClobClient.post_order))

except ImportError:
    print("Could not import ClobClient.")
