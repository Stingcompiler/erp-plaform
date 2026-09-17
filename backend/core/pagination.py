"""Page-number pagination with a client-chosen, capped page size.

The default 50 kept every list short, but a picker (customers at the POS,
suppliers on a bill) needs the whole set; without `page_size` the client
silently saw the first 50 and no more. 500 caps what one request may pull.
"""

from rest_framework.pagination import PageNumberPagination


class CappedPageNumberPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500
