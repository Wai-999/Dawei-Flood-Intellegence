"""Container readiness probe; no credential or operational details."""
from http.client import HTTPConnection
import os
from urllib.parse import urlsplit

def main():
    connection=HTTPConnection("127.0.0.1",8000,timeout=3)
    try:
        connection.request("GET","/health/ready",headers={"Host":urlsplit(os.environ["FLOOD_PUBLIC_ORIGIN"]).netloc})
        response=connection.getresponse()
        if response.status!=200: raise SystemExit(1)
        response.read()
    finally:connection.close()

if __name__=="__main__":main()
