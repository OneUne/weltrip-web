from django.shortcuts import render, redirect
from django.http import HttpResponse

# 검색 모듈과 연결 - 작성자:이혜인
from .forms import searchForm
from search.models import SearchMeta, SearchObj
from search.search import *
from search.rq_class import *
from actualPlanner.models import *
from django.db.models import Avg, Count, Q
import datetime 

#컨텐츠 추천 모듈과 연결 - 작성자: 김기정
from recs.content_based_recommender import *
from django.template.defaulttags import register
from collector.datas import *
from profile import Profile

#사용자 추천 모듈과 연결 - 작성자: 원윤희
from users.models import Profile
from recommender.views import similar_users


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


def home(request):
    # 인기장소 표출 - 작성자: 이혜인
    appinfo = ApiInfo('1a%2FLc1roxNrXp8QeIitbwvJdfpUYIFTcrbii4inJk3m%2BVpFvZSWjHFmOfWiH9T7TMbv07j5sDnJ5yefVDqHXfA%3D%3D', 'http://api.visitkorea.or.kr/openapi/service/rest/KorWithService/')
    sites = popularSites(8, True, appinfo)
    sites1 = sites[0:4]
    sites2 = sites[4:8]

    # 사용자 기반 협업 필터링 - 작성자 : 원윤희
    if request.user.is_authenticated :
        # 평점 기반 유사 사용자가 있는 경우
        if len(similar_users('%s' %request.user)['topn']) >= 2 : 
            targetUser = similar_users('%s' %request.user)['topn'][1][0]
            targetRating = Rating.objects.filter(Q(userRated = targetUser)&Q(grade__gte = 4))
            myRating = Rating.objects.filter(userRated = request.user)
            
            targetContents = [i.contentName for i in targetRating]
            myContents = [i.contentName for i in myRating]

            recs = [ i for i in targetContents if i not in myContents ]
            if len(recs) < 4 :
                if len(similar_users('%s' %request.user)['topn']) >= 3 : 
                    targetUser = similar_users('%s' %request.user)['topn'][2][0]
                    targetRating = Rating.objects.filter(Q(userRated = targetUser)&Q(grade__gte = 4))
                    myRating = Rating.objects.filter(userRated = request.user)
                    
                    targetContents = [i.contentName for i in targetRating]
                    myContents = [i.contentName for i in myRating]

                    for i in targetContents :
                        if i not in myContents :
                            recs.append(i)

            sites3 = simUserSites(recs, len(recs), True, appinfo)
            if len(recs) >= 4:
                sites3 = sites3[:4]
        
        # 신규 사용자의 경우
        else:
            userType = Profile.objects.filter(user_id = 32).values('disability')[0]['disability'][0]
            userPref = Profile.objects.filter(user_id = 32).values('preference')[0]['preference'][0]
            typeFilter = {'disability__startswith':userType, 'preference__startswith':userPref}
            sameType = Profile.objects.filter(**typeFilter).values('user_id')
            
            if len(sameType) == 0 :
                typeFilter = {'disability__startswith':userType}
                sameType = Profile.objects.filter(**typeFilter)
                if len(sameType) == 0 : sites3 = []

            targetRating = Rating.objects.filter(Q(userRated__in = sameType)&Q(grade__gte = 4))
            if len(targetRating) == 0 :
                sites3 = []
            else:
                myRating = Rating.objects.filter(userRated = request.user)
            
                targetContents = [i.contentName for i in targetRating]
                myContents = [i.contentName for i in myRating]

                recs = [ i for i in targetContents if i not in myContents ]

                sites3 = simUserSites(recs, len(recs), True, appinfo)
                if len(recs) >= 4:
                    sites3 = sites3[:4]

    #추천 장소 출력 - 작성자: 김기정
    if request.user.is_authenticated and not(userHisTable(request.user.username).empty): 
        recKey = int(userHisTable(request.user.username)['contentId'].iloc[-1]) #322836 ##테스트용 키
        recSpots = get_recommend_place_list_content(data, recKey)
        dicSpots = list(recSpots.to_dict().values())
        recimg = dicSpots[8]
        rectitle = dicSpots[17]
        recaddr = dicSpots[0]
        reckeys = list(recimg.keys())
        return render(request, 'planner/home.html', context = {'popular1': sites1, 'popular2' : sites2, 'userCF' : sites3, 'recimg' : recimg, 'rectitle' : rectitle, 'recaddr' : recaddr, 'recSpots' : recSpots, 'reckeys' : reckeys,})
    else:
        return render(request, 'planner/home.html', {'popular1': sites1, 'popular2' : sites2,})

def connect_search(request):
    if request.method == 'POST':
        form = searchForm(request.POST)
        metaInfo = ApiInfo('1a%2FLc1roxNrXp8QeIitbwvJdfpUYIFTcrbii4inJk3m%2BVpFvZSWjHFmOfWiH9T7TMbv07j5sDnJ5yefVDqHXfA%3D%3D', 'http://api.visitkorea.or.kr/openapi/service/rest/KorWithService/')

        if not (request.POST.get('keyword','') == ''):
            
            meta = SearchMeta(key = request.POST['keyword'], user = request.user, date = datetime.datetime.today())
            meta.save()

            # 결과 처리
            k_result = searchByKeyword(meta.key, metaInfo)
            searchObj = SearchObj()
            searchObj.key = meta.key
            searchObj.content = k_result

            # 상세페이지 출력 위한 결과 처리
            details = []
            for elm in k_result:
                tmp = getInfos(elm)
                details.append(tmp)
            details = checkInfos(details, 'title')
            rating_tmps = basicTable()

            for elm in details:
                # 각종 코드 한글명으로 치환
                findGeo(geo_df, elm)
                findSer(ser_df, elm)

                # 평점 데이터 조회
                try:
                    elm['rating_count'] = rating_tmps.at['_count_', str(elm.get('contentid'))]
                    elm['rating_avr'] = round(rating_tmps.at['_average_', str(elm.get('contentid'))], 2)
                except:
                    elm['rating_count'] = '0'
                    elm['rating_avr'] = '0'

            # 무장애정보 조회
            metaInfo.setUrl('http://api.visitkorea.or.kr/openapi/service/rest/KorWithService/')
            for elm in details:
                bfinfo = searchBF(elm['contentid'], metaInfo)
                elm['BF'] = bfinfo
            

            # 결과 페이지로 이동
            return render(request, 'search/search_result.html', {'SearchObj':searchObj, 'SearchMeta':meta, 'details': details, 'tag_names':tag_names, 'bf_tags':bf_tags,})
    
    else:
        form = searchForm()
        return render(request, 'planner/home.html', {'form':form})