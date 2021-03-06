# reco.py
import os
import random
import sys
import time
import numpy as np

import falcon
import operator
import pandas as pd

print(os.getcwd())
sys.path.insert(0, os.getcwd() + '/../')

from core.interaction_index import InteractionIndex
from core.interaction_mapper import InteractionMapper
from falcon_rest_api.multi_config import MultiConfig
from falcon_rest_api.ewma import EWMA
from falcon_rest_api.cnt import CNT

#
# import os
# import psutil
# process = psutil.Process(os.getpid())
# print(process.memory_info().rss)

cf = MultiConfig([
    # "/home/chambroc/Desktop/RecoResults/ThreeInARow/day1/interaction_indexing",
    # "/home/chambroc/Desktop/RecoResults/ThreeInARow/day2/interaction_indexing",
    # "/home/chambroc/Desktop/RecoResults/ThreeInARow/day3/interaction_indexing",
    # "/home/chambroc/Desktop/RecoResults/ThreeInARow120/day1/interaction_indexing",
    "/home/chambroc/Desktop/RecoResults/ThreeInARow120/day2/interaction_indexing",
    "/home/chambroc/Desktop/RecoResults/ThreeInARow120/day3/interaction_indexing",
    # "/home/chambroc/Desktop/RecoResults/ThreeInARowMoreEvents/day1/interaction_indexing",
    "/home/chambroc/Desktop/RecoResults/ThreeInARowMoreEvents/day2/interaction_indexing",
    "/home/chambroc/Desktop/RecoResults/ThreeInARowMoreEvents/day3/interaction_indexing",
])
cf.method='ghtree'
print("building maps and indices......")
iis = []
for dir in cf.source_dirs:
    print(dir)
    im = InteractionMapper(map_path=dir)
    print("...map ready")
    print("building index...")
    pd_df = pd.read_csv(dir + "/interaction_index.txt", header=None)
    for col in pd_df.columns:
        pd_df[col] = pd_df[col].astype(float)
    iis = iis + [InteractionIndex(im, pd_df.values, method=cf.method, space=cf.space)]
    print("...index ready")

num_classes = iis[0].im.interaction_class_cnt
ewma_dt = EWMA(100)
ewma_frac = EWMA(10000)
cnt = CNT()
jaccard_cnt = CNT()
tot_jaccard = CNT()


class RecoResource(object):
    def on_get(self, req, resp):
        t = time.time()
        resp.status = falcon.HTTP_200
        request_url = req.get_param('url')
        k_val = int(req.get_param('k', default=10))
        multi_results = [ii.knn_interaction_query(request_url, k=k_val)[0] for ii in iis]
        intersecting_results = list(
            set(multi_results[0]).intersection(*[set(res) for res in multi_results[1:len(multi_results)]]))
        union_res = set().union(*[set(s) for s in multi_results])
        resulting_merge = dict()
        for res in union_res:
            resulting_merge[res] = 0
            for q_res in multi_results:
                if res in q_res:
                    resulting_merge[res] = resulting_merge[res] + 1
        resulting_merge_tups = sorted(resulting_merge.items(), key=operator.itemgetter(1), reverse=True)
        ret_dict = {'url': request_url,
                    'sources': cf.source_dirs,
                    'intersecting_results': intersecting_results,
                    'weighted results': resulting_merge_tups}
        for idx, res in enumerate(multi_results):
            ret_dict['knn_urls_' + str(idx)] = list(res)
        resp.media = ret_dict
        # PROFILING FROM HERE:
        dt = time.time() - t
        if dt > 0.05:
            bucket = np.array([0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        elif dt > 0.01:
            bucket = np.array([100.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
        elif dt > 0.005:
            bucket = np.array([100.0, 100.0, 0.0, 0.0, 0.0], dtype=np.float32)
        elif dt > 0.001:
            bucket = np.array([100.0, 100.0, 100.0, 0.0, 0.0], dtype=np.float32)
        elif dt > 0.0005:
            bucket = np.array([100.0, 100.0, 100.0, 100.0, 0.0], dtype=np.float32)
        else:
            bucket = np.array([100.0, 100.0, 100.0, 100.0, 100.0], dtype=np.float32)
        ewma_dt.step(dt)
        ewma_frac.step(bucket)
        cnt.step(1)


class DrawRandomResource(object):
    def on_get(self, req, resp):
        resp.status = falcon.HTTP_200
        k_val = int(req.get_param('k', default=10))
        random_url_idx = random.randint(0, num_classes)
        url_str = iis[0].im.num_to_interaction(random_url_idx)
        multi_results = [ii.knn_idx_query(random_url_idx, k=k_val)[0] for ii in iis]
        intersecting_results = list(
            set(multi_results[0]).intersection(*[set(res) for res in multi_results[1:len(multi_results)]]))
        union_res = set().union(*[set(s) for s in multi_results])
        resulting_merge = dict()
        for res in union_res:
            resulting_merge[res] = 0
            for q_res in multi_results:
                if res in q_res:
                    resulting_merge[res] = resulting_merge[res] + 1
        resulting_merge_tups = sorted(resulting_merge.items(), key=operator.itemgetter(1), reverse=True)
        ret_dict = {'url': url_str,
                    'sources': cf.source_dirs,
                    'intersecting_results': intersecting_results,
                    'weighted results': resulting_merge_tups}
        for idx, res in enumerate(multi_results):
            ret_dict['knn_urls_' + str(idx)] = list(res)
        resp.media = ret_dict


class JaccardResource(object):
    def on_get(self, req, resp):
        resp.status = falcon.HTTP_200
        request_url = req.get_param('url')
        k_val = int(req.get_param('k', default=10))
        multi_results = [ii.knn_interaction_query(request_url, k=k_val) for ii in iis]
        ret_dict = {'url': request_url,
                    'sources': cf.source_dirs}
        all_jaccard = np.array([])
        for i in range(len(multi_results)):
            for j in range(i + 1, len(multi_results)):
                a = set(multi_results[i][0])
                b = set(multi_results[j][0])
                union_len = len(a.union(a, b))
                intersec_len = len(a.intersection(b))
                jd = 1 - intersec_len / union_len
                ret_dict[str(i) + "vs" + str(j)] = jd
                all_jaccard = np.append(all_jaccard, jd)
            resp.media = ret_dict
        tot_jaccard.step(all_jaccard)
        jaccard_cnt.step(1)


class JaccardRandomResource(object):
    def on_get(self, req, resp):

        resp.status = falcon.HTTP_200
        k_val = int(req.get_param('k', default=10))

        random_url_idx = random.randint(0, num_classes)
        url_str = iis[0].im.num_to_interaction(random_url_idx)
        multi_results = [ii.knn_idx_query(random_url_idx, k=k_val)[0] for ii in iis]

        ret_dict = {'url': url_str,
                    'sources': cf.source_dirs}
        all_jaccard = np.array([])
        for i in range(len(multi_results)):
            for j in range(i + 1, len(multi_results)):
                a = set(multi_results[i])
                b = set(multi_results[j])
                union_len = len(a.union(a, b))
                intersec_len = len(a.intersection(b))
                jd = 1 - intersec_len / union_len
                ret_dict[str(i) + "vs" + str(j)] = jd
                all_jaccard = np.append(all_jaccard, jd)
            resp.media = ret_dict

        tot_jaccard.step(all_jaccard)
        jaccard_cnt.step(1)


class MetricsResource(object):
    def on_get(self, req, resp):
        """Handles GET requests"""
        resp.status = falcon.HTTP_200
        dt_avg = ewma_dt.values
        resp.media = {
            'average_last_100_request_duration_in_s': dt_avg,
            'total_calls': cnt.values,
            'jaccard_cnt': jaccard_cnt.values,
            'jaccard_avgs': list(tot_jaccard.values / jaccard_cnt.values),
            'perc_last_10000_below_50ms': float(ewma_frac(0)),
            'perc_last_10000_below_10ms': float(ewma_frac(1)),
            'perc_last_10000_below_5ms': float(ewma_frac(2)),
            'perc_last_10000_below_1ms': float(ewma_frac(3)),
            'perc_last_10000_below_0.5ms': float(ewma_frac(4))
        }


class WhatWouldCarlSay(object):
    def on_get(self, req, resp):
        """Handles GET requests"""
        resp.status = falcon.HTTP_200
        dt_avg_in_s = ewma_dt.values
        if dt_avg_in_s is None:
            statement = "no traffic means, it's fast enough"
        elif dt_avg_in_s * 1000 < 5:
            statement = "this is fine"
        elif dt_avg_in_s * 1000 < 10:
            statement = "you can do better"
        else:
            statement = "your mama is faster than this"
        resp.media = {
            'statement': statement
        }


application = falcon.API()
application.add_route('/reco', RecoResource())
application.add_route('/randomreco', DrawRandomResource())
application.add_route('/metrics', MetricsResource())
application.add_route('/jaccard', JaccardResource())
application.add_route('/randomjaccard', JaccardRandomResource())
application.add_route('/whatwouldcarlsay', WhatWouldCarlSay())
