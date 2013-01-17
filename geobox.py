#!/usr/bin/env python
#
# Copyright 2008 Brett Slatkin
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

"""Defines the 'geobox' model and how to query on it.

It's hard to do bounding-box queries with non-relational databases because
they do not have the histograms necessary for using multiple inequality
filters in the same query.

Geobox queries get around this by pre-computing different resolutions of
bounding boxes and saving those in the database. Then to query for a bounding
box, you just query for the resolution of geo box that you're interested in.

A geobox is defined by a string ordered "lat|lon|lat|lon" that looks like:
  "37.78452999999|-122.39532395324|37.78452999998|-122.39532395323"

Where the two sets of coordinates form a bounding box. The first coordinate set
is the west/north-most corner of the bounding box. The second coordinate set is
the east/south-most corner of the bounding box.

Each geo value is represented with many decimal places of accuracy, up to the
resolution of the data source. The number of decimal places present for latitude
and longitude is called the "resolution" of the geobox. For example, 15
decimal-point values would be called "resolution 15". Each coordinate in the
geobox must have all digits defined for its corresponding resolution. That means
even trailing zeros should be present.

To query for members of a bounding box, we start with some input coordinates
like lat=37.78452 long=-122.39532 (both resolution 5). We then round these
coordinates up and down to the nearest "slice" to generate a geobox. A "slice"
is how finely to divide each level of resolution in the geobox. The minimum
slice size is 1, the maximum does not have a limit, since larger slices will
just spill over into lower resolutions (hopefully the examples will explain).

Some examples:

resolution=5, slice=2, and lat=37.78452 long=-122.39532:
  "37.78452|-122.39532|37.78450|-122.39530"

resolution=5, slice=10, and lat=37.78452 long=-122.39532:
  "37.78460|-122.39540|37.78450|-122.39530"

resolution=5, slice=25, and lat=37.78452 long=-122.39532:
  "37.78475|-122.39550|37.78450|-122.39525"


Another way to explain this is to say we compute a geobox for a point by
figuring out the closest known geobox that surrounds the point at the current
level of resolution

 ------------
|            |    x = actual point location (37.78, -122.39)
|            |    box = surrounding box (top=37.79, left=-122.39,
|      x     |                            bottom=37.78, right=-122.38)
|            |
 ------------


With App Engine, we can make this query fast by having a list property of
geobox strings associated with an entity. We can pre-compute the geobox for
all queryable entities at multiple resolutions and slices and add those to
the list property. Then the query is just an equals filter on the geobox string.

The great thing about using an equals filter is that we can use a geobox
query along with other equality and inequality filters to produce a rich
query that lets us find things in a bounding box that fit other criteria
(e.g., restaurants of a certain type in a location with a price range under
$20 per person).


Other techniques can be used to make geobox queries more accurate. For example,
if you compute the difference between a point's latitude and it's right and left
geobox coordinates, you can figure out how close to the edge of the box you are,
and possibly query the current box and the adjacent box in order to get data in
both areas:

 ------------ ------------
|            |            |
|           x|            |
|            |            |
|            |            |
 ------------ ------------
   Geobox 1      Geobox 2

This could also be extended to querying for multiple tiles if the point is
close to a corner of both latitude and longitude, which would result in four
geoboxes being queried in all:

 ------------ ------------
|            |            |
|            |            |
|            |            |
|           x|            |
 ------------ ------------
|            |            |
|            |            |
|            |            |
|            |            |
 ------------ ------------


Another technique is to query concentric geoboxes at the same time and do the
final ordering of results in memory. The success of this approach very much
depends on the amount of data returned by each query (since too much data in
the concentric boxes will overwhelm the in-memory sort).

 -----------
|  -------  |
| |  ---  | |
| | | x | | |
| |  ---  | |
|  -------  |
 -----------
"""

__author__ = "bslatkin@gmail.com (Brett Slatkin)"

__all__ = ["compute"]

import decimal


def _round_slice_down(coord, slice):
  try:
    remainder = coord % slice
    if coord > 0:
      return coord - remainder + slice
    else:
      return coord - remainder
  except decimal.InvalidOperation:
    # This happens when the slice is too small for the current coordinate.
    # That means we've already got zeros in the slice's position, so we're
    # already rounded down as far as we can go.
    return coord


def compute_tuple(lat, lon, resolution, slice):
  """Computes the tuple Geobox for a coordinate with a resolution and slice."""
  decimal.getcontext().prec = resolution + 3
  lat = decimal.Decimal(str(lat))
  lon = decimal.Decimal(str(lon))
  slice = decimal.Decimal(str(1.0 * slice * 10 ** -resolution))
  
  adjusted_lat = _round_slice_down(lat, slice)
  adjusted_lon = _round_slice_down(lon, slice)
  return (adjusted_lat, adjusted_lon - slice,
          adjusted_lat - slice, adjusted_lon)


def format_tuple(values, resolution):
  """Returns the string representation of a geobox tuple."""
  format = "%%0.%df" % resolution
  return "|".join(format % v for v in values)


def compute(lat, lon, resolution, slice):
  """Computes the Geobox for a coordinate with a resolution and slice."""
  return format_tuple(compute_tuple(lat, lon, resolution, slice), resolution)


def compute_set(lat, lon, resolution, slice):
  """Computes the set of adjacent Geoboxes for a coordinate."""
  decimal.getcontext().prec = resolution + 3
  primary_box = compute_tuple(lat, lon, resolution, slice)
  slice = decimal.Decimal(str(1.0 * slice * 10 ** -resolution))

  geobox_values = []
  for i in xrange(-1, 2):
    lat_delta = slice * i
    for j in xrange(-1, 2):
      lon_delta = slice * j
      adjusted_box = (primary_box[0] + lat_delta, primary_box[1] + lon_delta,
                      primary_box[2] + lat_delta, primary_box[3] + lon_delta)
      geobox_values.append(format_tuple(adjusted_box, resolution))

  return geobox_values


def test():
  tests = [
    (("37.78452", "-122.39532", 6, 10), "37.784530|-122.395330|37.784520|-122.395320"),
    (("37.78452", "-122.39532", 6, 25), "37.784525|-122.395325|37.784500|-122.395300"),
    (("37.78452", "-122.39532", 7, 25), "37.7845225|-122.3953225|37.7845200|-122.3953200"),
    (("37.78452", "-122.39532", 7, 1), "37.7845201|-122.3953201|37.7845200|-122.3953200"),
    (("37.78452", "-122.39532", 5, 15), "37.78455|-122.39535|37.78440|-122.39520"),
    (("37.78452", "-122.39532", 4, 17), "37.7859|-122.3966|37.7842|-122.3949"),
    (("37.78452", "-122.39531", 4, 17), "37.7859|-122.3966|37.7842|-122.3949"),
    (("37.78452", "-122.39667", 4, 17), "37.7859|-122.3983|37.7842|-122.3966"),
  ]
  for args, expected in tests:
    print "Testing compute%s, expecting %s" % (args, expected)
    value = compute(*args)
    assert value == expected, "Found: " + value
  
  expected = sorted([
    '37.784500|-122.395350|37.784475|-122.395325',
    '37.784500|-122.395325|37.784475|-122.395300',
    '37.784500|-122.395300|37.784475|-122.395275',
    '37.784525|-122.395350|37.784500|-122.395325',
    '37.784525|-122.395325|37.784500|-122.395300',
    '37.784525|-122.395300|37.784500|-122.395275',
    '37.784550|-122.395350|37.784525|-122.395325',
    '37.784550|-122.395325|37.784525|-122.395300',
    '37.784550|-122.395300|37.784525|-122.395275'
  ])
  print "Testing compute_set, expecting %s" % expected
  value = sorted(compute_set("37.78452", "-122.39532", 6, 25))
  assert value == expected, "Failed, found: " + value
  print "Tests passed"


if __name__ == "__main__":
  test()
