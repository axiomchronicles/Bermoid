from exceptions.http.core import MethodNotAllowed
from shortcuts import render, redirect

async def main(request):
    request.session['user'] = 'guest'
    return await redirect('/dashboard', status_code = 302)

async def get_session(request):
    return dict(request.session)