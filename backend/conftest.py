"""Suite-wide test setup. Runs before any test module imports main.

Rate limits are OFF for the suite: hundreds of tests share one TestClient
"IP", so a real budget would trip on accumulated calls from unrelated tests
and fail them at random. The rate-limit tests themselves flip limits back on
with their own tiny limiters, so the behavior is still fully covered.
"""

import os

os.environ["CUE_RATE_LIMITS"] = "off"
