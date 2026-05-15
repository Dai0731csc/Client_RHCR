if __name__ == "__main__":
    from aiohttp import web

    from backend import HOST, PORT, create_app, create_ssl_context

    print(f"HTTPS + WSS server running at https://{HOST}:{PORT}")
    web.run_app(create_app(), host=HOST, port=PORT, ssl_context=create_ssl_context())
