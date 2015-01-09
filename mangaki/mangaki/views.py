from django.views.generic.detail import DetailView
from django.views.generic.list import ListView
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse, Http404
from mangaki.models import Work, Anime, Rating, Page, Profile
from collections import Counter
from markdown import markdown
from secret import DISCOURSE_API_USERNAME, DISCOURSE_API_KEY
from pydiscourse.client import DiscourseClient
import datetime
import random
import json

class AnimeDetail(DetailView):
    model = Anime
    def get_context_data(self, **kwargs):
        context = super(AnimeDetail, self).get_context_data(**kwargs)
        context['object'].source = context['object'].source.split(',')[0]
        if self.request.user.is_authenticated():
            try:
                context['rating'] = self.object.rating_set.get(user=self.request.user).choice
            except Rating.DoesNotExist:
                pass
        return context

class AnimeList(ListView):
    model = Anime
    context_object_name = 'anime'
    def get_queryset(self):
        return Anime.objects.order_by('title') if 'alpha' in self.kwargs['mode'] else Anime.objects.all()
    def get_context_data(self, **kwargs):
        context = super(AnimeList, self).get_context_data(**kwargs)
        context['mode'] = self.kwargs['mode']
        context['template_mode'] = 'work_no_poster.html' if 'flat' in self.kwargs['mode'] else 'work_poster.html'
        if self.request.user.is_authenticated():
            for obj in context['object_list']:
                try:
                    obj.rating = obj.rating_set.get(user=self.request.user).choice
                except Rating.DoesNotExist:
                    pass
        return context 

def get_avatar(email):
    client = DiscourseClient('http://meta.mangaki.fr', api_username=DISCOURSE_API_USERNAME, api_key=DISCOURSE_API_KEY)
    users = client._get('/admin/users/list/active.json?show_emails=true')
    for user in users:
        if user['email'] == email:
            return user['avatar_template']

class RatingList(ListView):
    model = Rating
    def get_queryset(self):
        if self.request.user.username == self.kwargs['username'] or Profile.objects.get(user__username=self.kwargs['username']).is_shared:
            return Rating.objects.filter(user__username=self.kwargs['username'])
        else:
            return Rating.objects.none()
    def get_context_data(self, **kwargs):
        ordering = ['willsee', 'like', 'neutral', 'dislike', 'wontsee']
        context = super(RatingList, self).get_context_data(**kwargs)
        context['username'] = self.kwargs['username']
        context['avatar_url'] = 'http://meta.mangaki.fr' + get_avatar(User.objects.get(username=self.kwargs['username']).email).format(size=150)
        context['object_list'] = sorted(context['object_list'], key=lambda x: ordering.index(x.choice))
        return context

def index(request):
    if request.user.is_authenticated():
        return redirect('/anime/')
    return render(request, 'index.html')

def rate_work(request, work_id):
    if request.user.is_authenticated() and request.method == 'POST':
        work = get_object_or_404(Work, id=work_id)
        Rating.objects.update_or_create(user=request.user, work=work, defaults={'choice': request.POST['choice']})
        return HttpResponse(request.POST['choice'])
    return HttpResponse()

class MarkdownView(DetailView):
    model = Page
    slug_field = 'name'
    template_name = 'static.html'
    def get_context_data(self, **kwargs):
        page = super(MarkdownView, self).get_object()
        return {'html': markdown(page.markdown)}

def get_works(request, category):
    if category == 'anime':
        data = []
        for anime in Anime.objects.all():
            data.append({'id': anime.id, 'description': 'Test', 'value': anime.title, 'tokens': anime.title.lower().split(), 'year': 2014})
        return HttpResponse(json.dumps(data), content_type='application/json')
    return HttpResponse()

def get_recommendations(user):
    contest = []
    values = {'like': 2, 'dislike': -2, 'neutral': 0.1, 'willsee': 0.5, 'wontsee': -0.5}
    neighbors = Counter()
    for my in Rating.objects.filter(user=user):
        for her in Rating.objects.filter(work=my.work):
            neighbors[her.user.id] = values[my.choice] * values[her.choice]
    works = Counter()
    nb_ratings = {}
    for user_id, score in neighbors.most_common(10):
        for her in Rating.objects.filter(user__id=user_id):
            if her.work.id not in works:
                works[her.work.id] = [values[her.choice], neighbors[her.user.id]]
                nb_ratings[her.work.id] = 1
            else:
                works[her.work.id][0] += values[her.choice]
                works[her.work.id][1] += score
                nb_ratings[her.work.id] += 1
    for work_id in works:
        if nb_ratings[work_id] == 1 or (Rating.objects.filter(user=user, work__id=work_id).count() != 0 and Rating.objects.filter(user=user, work__id=work_id, choice='willsee').count() == 0):
            works[work_id] = (0, 0)
        else:
            # print(Work.objects.get(id=work_id).title, Rating.objects.filter(user=user, work__id=work_id).count(), )
            works[work_id] = (float(works[work_id][0]) / nb_ratings[work_id], works[work_id][1])
    return works.most_common(4)

@login_required
def get_reco(request):
    reco_list = []
    for work_id, _ in get_recommendations(request.user):
        reco = Anime.objects.get(id=work_id)
        if Rating.objects.filter(user=request.user, work__id=work_id).count() != 0:
            reco_list.append((reco, 'willsee'))
        else:
            reco_list.append((reco, ''))
    return render(request, 'mangaki/reco_list.html', {'reco_list': reco_list})

def update_shared(request):
    if request.user.is_authenticated() and request.method == 'POST':
        Profile.objects.filter(user=request.user).update(is_shared=request.POST['is_shared'] == 'true')
    return HttpResponse()
