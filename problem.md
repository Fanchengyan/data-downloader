ASF Authentication Issues Summary
Problem Description
Downloading data from ASF (Alaska Satellite Facility) fails when using 
httpx
 or 
aiohttp
 engines, even with valid .netrc credentials. The error manifests as 401 Unauthorized or detection of "Server doesn't support range requests" (due to failed auth on HEAD requests).

Root Cause Analysis
ASF uses a complex OAuth 2.0 authentication flow involving multiple cross-domain redirects:

sentinel1-burst.asf.alaska.edu (Request)
auth.asf.alaska.edu (Redirect 302)
urs.earthdata.nasa.gov (Redirect 302 - OAuth Provider)
auth.asf.alaska.edu (Redirect 302 - Callback with code)
sentinel1-burst.asf.alaska.edu (Redirect 302 - With session cookie)
AWS S3 Bucket (Final Download URL)
Library Behavior
requests
 (Success): Automatically handles cookies and re-sends the Authorization header (from .netrc) or manages the OAuth session cookies correctly across these domains.
httpx
 / 
aiohttp
 (Failure):
Standard follow_redirects=True: Fails to persist the necessary authentication state (cookies/headers) across the domain hops, specifically when moving from Earthdata back to ASF.
Custom 
NetrcAuth
 (Attempted Fix): Manually re-applying .netrc credentials at each redirect step does not fully resolve the issue, likely because the flow relies on cookies set during the urs.earthdata.nasa.gov step which are not being correctly securely passed or accepted in the subsequent requests by these async clients.
Findings
Tests Configured:

test_asf_redirect.py
: Confirmed failure with 
httpx
/
aiohttp
.
inspect_requests_auth.py
: Confirmed 
requests
 success and analyzed its redirect chain.
Conclusion:

Solving this with 
httpx
/
aiohttp
 requires re-implementing a full OAuth/Session-aware redirect handler which is complex and error-prone.
The 
requests
 library "just works" for this case.