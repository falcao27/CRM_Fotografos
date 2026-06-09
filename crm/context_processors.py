def crm_brand(request):
    user = getattr(request, "user", None)
    nome = "CRM Cloud"
    subtitulo = "Acesso ao sistema"

    if user and user.is_authenticated:
        perfil = getattr(user, "perfil_crm", None)
        if perfil and perfil.admin_master:
            nome = "Admin Master"
            subtitulo = "Painel administrativo"
        elif perfil and perfil.empresa:
            nome = perfil.empresa.nome
            subtitulo = "Vendas e relacionamento"
        elif user.get_full_name():
            nome = user.get_full_name()
        else:
            nome = user.username

    palavras = [parte for parte in nome.replace("-", " ").split() if parte]
    if len(palavras) >= 2:
        iniciais = "".join(parte[0] for parte in palavras[:2]).upper()
    else:
        iniciais = nome[:2].upper()

    return {
        "crm_brand_nome": nome,
        "crm_brand_titulo": f"CRM {nome}" if nome != "Admin Master" else nome,
        "crm_brand_subtitulo": subtitulo,
        "crm_brand_iniciais": iniciais,
    }
