import json

from .core import LocalFixture, probe


def main():
    with LocalFixture() as server:
        variants={'allowed':{},'bad_host':{'host_override':'unrelated.invalid'},
                  'bad_origin':{'origin':'https://unapproved.invalid'},
                  'bad_auth':{'bearer':'WRONG-SYNTHETIC'},
                  'bad_origin_and_auth':{'origin':'https://unapproved.invalid','bearer':'WRONG-SYNTHETIC'}}
        output={case:probe(server.url,trusted_fixture=True,**kwargs) for case,kwargs in variants.items()}
    with LocalFixture(disclose_reason=False) as server:
        output['stripped_metadata']=probe(server.url,origin='https://unapproved.invalid',trusted_fixture=True)
    print(json.dumps({'mode':'controlled-loopback-fixture','results':output,
                      'claim_boundary':'This teaching fixture does not exercise an MCP SDK or proxy; native reproduction is a separate gate.'},indent=2,sort_keys=True))


if __name__=='__main__':main()
