import re

try:
	import lxml.etree as ET
except ImportError, ex:
	ex.args = '%s; please install the python-lxml package <http://codespeak.net/lxml/>' % str(ex),
	raise

try:
	from djvu import sexpr
	from djvu import const
except ImportError, ex:
	ex.args = '%s; please install the python-djvulibre package' % str(ex),
	raise

from image_size import get_image_size

hocr_class_to_djvu = \
dict(
	ocr_page = const.TEXT_ZONE_PAGE,
	ocr_column = const.TEXT_ZONE_COLUMN,
	ocr_carea = const.TEXT_ZONE_COLUMN,
	ocr_par = const.TEXT_ZONE_PARAGRAPH,
	ocr_line = const.TEXT_ZONE_LINE,
	ocrx_block = const.TEXT_ZONE_REGION,
	ocrx_line = const.TEXT_ZONE_LINE,
	ocrx_word = const.TEXT_ZONE_WORD
).get

IMAGE_RE = re.compile(
	r'''
		image \s+ (?P<file_name> \S+)
	''', re.VERBOSE)

BBOX_RE = re.compile(
	r'''
		bbox \s+
		(?P<x0> \d+) \s+ 
		(?P<y0> \d+) \s+
		(?P<x1> \d+) \s+
		(?P<y1> \d+)
	''', re.VERBOSE)

class BBox(object):

	def __init__(self, x0 = None, y0 = None, x1 = None, y1 = None):
		self._coordinates = [x0, y0, x1, y1]
	
	@property
	def x0(self): return self[0]

	@property
	def y0(self): return self[1]

	@property
	def x1(self): return self[2]

	@property
	def y1(self): return self[3]

	def __getitem__(self, item):
		return self._coordinates[item]

	def __nonzero__(self):
		for value in self._coordinates:
			if value is None:
				return False
		return True
	
	def __repr__(self):
		return '%s(%r, %r, %r, %r)' % ((self.__class__.__name__,) + tuple(self._coordinates))

	def update(self, bbox):
		for i, self_i in enumerate(self._coordinates):
			if self_i is None:
				self._coordinates[i] = bbox[i]
			elif i < 2 and bbox[i] is not None and self[i] > bbox[i]:
				self._coordinates[i] = bbox[i]
			elif i > 1 and bbox[i] is not None and self[i] < bbox[i]:
				self._coordinates[i] = bbox[i]

def _scan(node, buffer, parent_bbox, page_height = None):
	def look_down(buffer, parent_bbox):
		for child in node.iterchildren():
			_scan(child, buffer, parent_bbox, page_height)
			if node.tail and node.tail.strip():
				buffer.append(node.tail)
		if node.text and node.text.strip():
			buffer.append(node.text)
	if not isinstance(node.tag, basestring):
		return
	hocr_classes = (node.get('class') or '').split()
	djvu_class = None
	for hocr_class in hocr_classes:
		djvu_class = hocr_class_to_djvu(hocr_class)
		if djvu_class:
			break
	if djvu_class:
		title = node.get('title') or ''
		m = BBOX_RE.search(title)
		if m is None:
			bbox = BBox()
		else:
			bbox = BBox(*(int(m.group(id)) for id in ('x0', 'y0', 'x1', 'y1')))
			parent_bbox.update(bbox)
	if djvu_class:
		if djvu_class is const.TEXT_ZONE_PAGE:
			if not bbox:
				m = IMAGE_RE.search(title)
				if m is None:
					raise Exception("Cannot determine page's bbox")
				page_width, page_height = get_image_size(m.group('file_name'))
				bbox = BBox(0, 0, page_width - 1, page_height - 1)
				parent_bbox.update(bbox)
			else:
				if (bbox.x0, bbox.y0) != (0, 0):
					raise Exception("Page's bbox should start with (0, 0)")
				page_width, page_height = bbox.x1, bbox.y1
		result = [sexpr.Symbol(djvu_class)]
		result += [None] * 4
		look_down(result, bbox)
		if not bbox and not len(node):
			return
		if page_height is None:
			raise Exception('Unable to determine page height')
		result[1] = bbox.x0
		result[2] = page_height - 1 - bbox.y1
		result[3] = bbox.x1
		result[4] = page_height - 1 - bbox.y0
		if len(result) == 5:
			result.append('')
		buffer.append(result)
	else:
		look_down(buffer, parent_bbox)

def scan(node):
	buffer = []
	_scan(node, buffer, BBox())
	return buffer

def extract_text(stream):
	doc = ET.parse(stream, ET.HTMLParser())
	scan_result = scan(doc.find('/body'))
	return sexpr.Expression(scan_result)

# vim:ts=4 sw=4 noet