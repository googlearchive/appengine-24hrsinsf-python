import logging
import math
from google.appengine.ext import db
from google.appengine.ext.db import djangoforms

import geobox

RADIUS = 6378100

GEOBOX_CONFIGS = (
  (4, 5, True),
  (3, 2, True),
  (3, 8, False),
  (3, 16, False),
  (2, 5, False),
)

_DAY_DICTIONARY = {
  'Monday': 'hr_mon',
  'Tuesday': 'hr_tues',
  'Wednesday': 'hr_weds',
  'Thursday': 'hr_thurs',
  'Friday': 'hr_fri',
  'Saturday': 'hr_sat',
  'Sunday': 'hr_sun'
}
def _make_hours(store_hours):
  """Store hours is a dictionary that maps a DOW to different open/close times
     Since it's easy to represent disjoing hours, we'll do this by default
     Such as, if a store is open from 11am-2pm and then 5pm-10pm
     We'll slice the times in to a list of floats representing 30 minute intevals
     So for monday, let's assume we have the store hours from 10am - 3pm
     We represent this as
     monday = [10.0, 10.5, 11.0, 11.5, 12.0, 12.5, 13.0, 13.5, 14.0, 14.5]
  """
  week_hrs = {}
  for dow in store_hours.keys():
    dow_hours = []
    for hour_set in store_hours[dow]:
      if len(hour_set) < 2:
        open_hr = 0.0
        close_hr = 24.0
      else:
        open_hr = float(hour_set[0])
        close_hr = float(hour_set[1])
      if close_hr < open_hr:
        tmp = close_hr
        close_hr = open_hr
        open_hr = tmp
      current_hr_it = open_hr
      while((close_hr - current_hr_it) >= .5):
        dow_hours.append(current_hr_it)
        current_hr_it += .5
    week_hrs[dow] = dow_hours
  return week_hrs

def _earth_distance(lat1, lon1, lat2, lon2):
  lat1, lon1 = math.radians(float(lat1)), math.radians(float(lon1))
  lat2, lon2 = math.radians(float(lat2)), math.radians(float(lon2))
  return RADIUS * math.acos(math.sin(lat1) * math.sin(lat2) +
      math.cos(lat1) * math.cos(lat2) * math.cos(lon2 - lon1))

class Store(db.Model):
  name = db.StringProperty()
  pretty_address = db.TextProperty()
  pretty_description = db.TextProperty()
  pretty_hours = db.TextProperty()
  location = db.GeoPtProperty()
  geoboxes = db.StringListProperty()
  hr_mon = db.ListProperty(float)
  hr_tues = db.ListProperty(float)
  hr_weds = db.ListProperty(float)
  hr_thurs = db.ListProperty(float)
  hr_fri = db.ListProperty(float)
  hr_sat = db.ListProperty(float)
  hr_sun = db.ListProperty(float)
  holidays = db.StringListProperty()
  categories = db.StringListProperty()
  phone_numbers = db.StringProperty()

  @classmethod
  def add(self, **kwargs):
    lat = kwargs.pop('lat')
    lon = kwargs.pop('lon')
    location = db.GeoPt(lat, lon)
    name = kwargs['name']
    new_store = Store(name=name, location=location)
    all_boxes = []
    new_store.pretty_address = kwargs['address']
    for (resolution, slice, use_set) in GEOBOX_CONFIGS:
      if use_set:
        all_boxes.extend(geobox.compute_set(lat, lon, resolution, slice))
      else:
        all_boxes.append(geobox.compute(lat, lon, resolution, slice))
    new_store.geoboxes = all_boxes
    store_hour_dict = _make_hours(kwargs['store_hours'])
    for day, prop in _DAY_DICTIONARY.iteritems():
      setattr(new_store, prop, store_hour_dict[day])

    new_store.categories = kwargs['categories']
    new_store.pretty_description = kwargs['description']
    new_store.put()

  @classmethod
  def query(self, time, dow, lat, lon, max_results, min_params):
    """Queries for Muni stops repeatedly until max results or scope is reached.
    Args:
      system: The transit system to query.
      lat, lon: Coordinates of the agent querying.
      max_results: Maximum number of stops to find.
      min_params: Tuple (resolution, slice) of the minimum resolution to allow.

    Returns:
      List of (distance, MuniStop) tuples, ordered by minimum distance first.
      There will be no duplicates in these results. Distance is in meters.
    """
    # Maps stop_ids to MuniStop instances.
    found_stores = {}

    # Do concentric queries until the max number of results is reached.
    dow_query_string = _DAY_DICTIONARY[dow] + ' ='
    for params in GEOBOX_CONFIGS:
      if len(found_stores) >= max_results:
        break
      if params < min_params:
        break

      resolution, slice, unused = params
      box = geobox.compute(lat, lon, resolution, slice)
      logging.info("Searching for box=%s at resolution=%s, slice=%s",
                    box, resolution, slice)
      query = self.all().filter("geoboxes =", box).filter(dow_query_string, time)
      results = query.fetch(50)
      logging.info("Found %d results", len(results))

      # De-dupe results.
      for result in results:
        if result.name not in found_stores:
          found_stores[result.name] = result

    # Now compute distances and sort by distance.
    stores_by_distance = []
    for store in found_stores.itervalues():
      distance = _earth_distance(lat, lon, store.location.lat, store.location.lon)
      stores_by_distance.append((distance, store))
    stores_by_distance.sort()

    return stores_by_distance

class UserProfile(db.Model):
  user = db.UserProperty(required=True)

class CommentIndex(db.Model):
  max_index = db.IntegerProperty(default=0, required=True)

class Comment(db.Model):
  index = db.IntegerProperty(required=True)
  reviewer = db.ReferenceProperty(UserProfile, required=True)
  store = db.ReferenceProperty(Store, required=True)
  review = db.TextProperty(required=True)
  rating = db.IntegerProperty(choices=set([1,2,3,4,5]))
  posted_on = db.DateTimeProperty(auto_now_add=True)
  disabled = db.BooleanProperty(default=False)