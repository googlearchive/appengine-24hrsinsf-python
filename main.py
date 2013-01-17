#!/usr/bin/env python
#
# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import wsgiref.handlers
import os
import logging
import math
from datetime import datetime
from datetime import timedelta

from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

import models

_DOW_DICT = {
  0: 'Monday',
  1: 'Tuesday',
  2: 'Wednesday',
  3: 'Thursday',
  4: 'Friday',
  5: 'Saturday',
  6: 'Sunday'  
}
def _floatify_time(current_time):
  dow_int = current_time.weekday()
  hour = float(current_time.hour)
  minute = current_time.minute
  if minute > 15:
    hour = hour + 0.5
  if minute > 45:
    hour = hour + 0.5
  if hour == 24.0:
    hour = 0.0
  return _DOW_DICT[dow_int], hour

def _human_readify_time(dow, float_time):
  ampm = 'AM'
  min_string = '00'
  floor_time = math.floor(float_time)
  delta = math.fabs(float_time - floor_time)
  if delta == .5:
    logging.info(delta)
    min_string = '30'
  if float_time > 12.5:
    ampm = 'PM'
    float_time = float_time - 12.0
  return '%s %i:%s %s' % (dow, int(floor_time), min_string, ampm)

class MainHandler(webapp.RequestHandler):

  def get(self):
    path = os.path.join(os.path.dirname(__file__), os.path.join('templates', 'find_me.html'))
    self.response.out.write(template.render(path, {}))

class FindMyBusiness(webapp.RequestHandler):
  def get(self):
    my_position_lat = 37.765914
    my_position_lon = -122.424817
    current_time = datetime.now() - timedelta(hours=8)
    dow_string, my_time = _floatify_time(current_time)
    logging.info(my_time)
    my_stores = models.Store.query(time=my_time, lat=my_position_lat, 
                                   dow=dow_string, lon=my_position_lon, max_results=2, 
                                   min_params=(2,0))
    for distance, store in my_stores:
      self.response.out.write(store.name)

  def post(self):
    user_pos_lat = float(self.request.get('lat'))
    user_pos_lon = float(self.request.get('lon'))
    time_string = self.request.get('time')
    day_string = self.request.get('dow')
    human_address = self.request.get('human_readable')

    if time_string and day_string:
      dow = _DOW_DICT[int(day_string)]
      my_time = float(time_string)
    else:
      current_time = datetime.now() - timedelta(hours=8)
      dow, my_time = _floatify_time(current_time)

    human_time = _human_readify_time(dow, my_time)

    my_stores = models.Store.query(time=my_time, lat=user_pos_lat, 
                                   dow=dow, lon=user_pos_lon, 
                                   max_results=2, min_params=(2,0))
    template_values = {'store_information': my_stores,
                       'human_address': human_address,
                       'human_time': human_time,
                       'user_lat': user_pos_lat, 
                       'user_lon': user_pos_lon}

    path = os.path.join(os.path.dirname(__file__), os.path.join('templates', 'display_locations.html'))
    self.response.out.write(template.render(path, template_values))

class AddBusiness(webapp.RequestHandler):
  def get(self):
    path = os.path.join(os.path.dirname(__file__), os.path.join('templates', 'add_business.html'))
    self.response.out.write(template.render(path, {}))

  def post(self):
    name = self.request.get('name')
    logging.info(name)
    address = self.request.get('address')
    description = self.request.get('description')
    lat = float(self.request.get('lat'))
    lon = float(self.request.get('lon'))
    hrs_dict = {}
    hrs_dict['Monday'] = [[int(self.request.get('monday_start')),
                          int(self.request.get('monday_end'))]]

    hrs_dict['Tuesday'] = [[int(self.request.get('tuesday_start')),
                          int(self.request.get('tuesday_end'))]]

    hrs_dict['Wednesday'] = [[int(self.request.get('wednesday_start')),
                          int(self.request.get('wednesday_end'))]]

    hrs_dict['Thursday'] = [[int(self.request.get('thursday_start')),
                          int(self.request.get('thursday_end'))]]

    hrs_dict['Friday'] = [[int(self.request.get('friday_start')),
                          int(self.request.get('friday_end'))]]

    hrs_dict['Saturday'] = [[int(self.request.get('saturday_start')),
                          int(self.request.get('saturday_end'))]]

    hrs_dict['Sunday'] = [[int(self.request.get('sunday_start')),
                          int(self.request.get('sunday_end'))]]
    categories = []
    for category in self.request.get('tags').split(','):
      if len(categories) < 3:
        categories.append(category)
    new_store = models.Store.add(name=name, address=address, lat=lat, lon=lon, store_hours=hrs_dict, categories=categories, description=description)
    self.response.out.write('done')

def main():
  application = webapp.WSGIApplication([('/', MainHandler),
                                        ('/add_biz', AddBusiness),
                                        ('/find', FindMyBusiness) ],
                                       debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
  main()
