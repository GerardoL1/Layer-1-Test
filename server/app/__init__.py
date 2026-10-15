"""
The recovery server, split by job:

  core/        database, size limits, turning values into JSON
  schemas/     request bodies the API accepts
  middleware/  the request size limit
  services/    the work behind the endpoints (reading exports, parsing payloads, processing)
  readiness/   the placeholder score, usual ranges and wording
  routers/     the endpoints, one file per screen or data route

main.py (one level up) builds the FastAPI app from these.
"""
