from core.pattern import path
from wrappers.responses import JsonResponse


async def home(request):
    return JsonResponse({"message": "Welcome!"})


urlpatterns = [
    path('/', home, name='home'),
]
