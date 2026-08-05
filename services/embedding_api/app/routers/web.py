from fastapi import APIRouter

from fastapi import Request

from fastapi.responses import HTMLResponse

from fastapi.templating import Jinja2Templates

router = APIRouter(

    tags=[

        "Web"

    ]

)

templates = Jinja2Templates(

    directory="app/templates"

)


@router.get(

    "/",

    response_class=HTMLResponse

)

async def index(

    request: Request

):

    return templates.TemplateResponse(

        request=request,

        name="index.html"

    )

@router.get(

    "/documents-ui",

    response_class=HTMLResponse

)

async def documents(

    request: Request

):

    return templates.TemplateResponse(

        request=request,

        name="documents.html"

    )


@router.get(

    "/query-ui",

    response_class=HTMLResponse

)

async def query(

    request: Request

):

    return templates.TemplateResponse(

        request=request,

        name="query.html"

    )