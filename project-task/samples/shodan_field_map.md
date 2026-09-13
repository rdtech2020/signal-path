# Shodan sample field map

Built from 15 records in `shodan_sample.jsonl`.
The full dump is Zstd NDJSON at `data/b2_download_file_by_id`.

| Field | Types in sample |
|---|---|
| `_shodan` | dict |
| `_shodan.crawler` | str |
| `_shodan.id` | str |
| `_shodan.module` | str |
| `_shodan.options` | dict |
| `_shodan.options.hostname` | str |
| `_shodan.ptr` | bool |
| `_shodan.region` | str |
| `asn` | str |
| `cloud` | dict |
| `cloud.provider` | str |
| `cloud.region` | str |
| `cloud.service` | NoneType, str |
| `cpe` | list |
| `cpe23` | list |
| `cpe23_hash` | int |
| `data` | str |
| `domains` | list |
| `hash` | int |
| `hostnames` | list |
| `http` | dict |
| `http.components` | dict |
| `http.components.Amazon CloudFront` | dict |
| `http.components.Amazon CloudFront.categories` | list |
| `http.components.Amazon S3` | dict |
| `http.components.Amazon S3.categories` | list |
| `http.components.Amazon Web Services` | dict |
| `http.components.Amazon Web Services.categories` | list |
| `http.components.Cloudflare` | dict |
| `http.components.Cloudflare Browser Insights` | dict |
| `http.components.Cloudflare Browser Insights.categories` | list |
| `http.components.Cloudflare.categories` | list |
| `http.components.Google Cloud` | dict |
| `http.components.Google Cloud CDN` | dict |
| `http.components.Google Cloud CDN.categories` | list |
| `http.components.Google Cloud.categories` | list |
| `http.components.HTTP/3` | dict |
| `http.components.HTTP/3.categories` | list |
| `http.components.LiteSpeed` | dict |
| `http.components.LiteSpeed Cache` | dict |
| `http.components.LiteSpeed Cache.categories` | list |
| `http.components.LiteSpeed.categories` | list |
| `http.components.Litespeed Cache` | dict |
| `http.components.Litespeed Cache.categories` | list |
| `http.components.Nginx` | dict |
| `http.components.Nginx.categories` | list |
| `http.components.Nginx.versions` | list |
| `http.components_hash` | int |
| `http.dom_hash` | int |
| `http.favicon` | dict |
| `http.favicon.data` | str |
| `http.favicon.hash` | int |
| `http.favicon.location` | str |
| `http.headers` | dict |
| `http.headers.accept-ranges` | str |
| `http.headers.age` | str |
| `http.headers.alt-svc` | str |
| `http.headers.cache-control` | str |
| `http.headers.cf-cache-status` | str |
| `http.headers.cf-ray` | str |
| `http.headers.connection` | str |
| `http.headers.content-length` | str |
| `http.headers.content-type` | str |
| `http.headers.date` | str |
| `http.headers.etag` | str |
| `http.headers.expires` | str |
| `http.headers.last-modified` | str |
| `http.headers.location` | str |
| `http.headers.nel` | str |
| `http.headers.referrer-policy` | str |
| `http.headers.report-to` | str |
| `http.headers.server` | str |
| `http.headers.server-timing` | str |
| `http.headers.transfer-encoding` | str |
| `http.headers.vary` | str |
| `http.headers.via` | str |
| `http.headers.x-amz-cf-id` | str |
| `http.headers.x-amz-cf-pop` | str |
| `http.headers.x-cache` | str |
| `http.headers.x-exc` | str |
| `http.headers.x-frame-options` | str |
| `http.headers.x-sc-h` | str |
| `http.headers.x-turbo-charged-by` | str |
| `http.headers.x-ws-request-id` | str |
| `http.headers_hash` | int |
| `http.host` | str |
| `http.html` | str |
| `http.html_hash` | int |
| `http.location` | str |
| `http.redirects` | list |
| `http.robots` | NoneType |
| `http.robots_hash` | NoneType |
| `http.securitytxt` | NoneType |
| `http.securitytxt_hash` | NoneType |
| `http.server` | str |
| `http.server_hash` | int |
| `http.sitemap` | NoneType |
| `http.sitemap_hash` | NoneType |
| `http.status` | int |
| `http.title` | NoneType, str |
| `http.title_hash` | NoneType, int |
| `http.waf` | str |
| `ip` | int |
| `ip_str` | str |
| `isp` | str |
| `location` | dict |
| `location.area_code` | NoneType |
| `location.city` | str |
| `location.country_code` | str |
| `location.country_name` | str |
| `location.latitude` | float |
| `location.longitude` | float |
| `location.region_code` | str |
| `opts` | dict |
| `opts.heartbleed` | str |
| `opts.raw` | str |
| `opts.vulns` | list |
| `org` | str |
| `os` | NoneType |
| `port` | int |
| `pptp` | dict |
| `pptp.firmware` | int |
| `pptp.hostname` | str |
| `pptp.vendor` | str |
| `product` | str |
| `ssl` | dict |
| `ssl.acceptable_cas` | list |
| `ssl.alpn` | list |
| `ssl.cert` | dict |
| `ssl.cert.expired` | bool |
| `ssl.cert.expires` | str |
| `ssl.cert.extensions` | list |
| `ssl.cert.extensions[].critical` | bool |
| `ssl.cert.extensions[].data` | str |
| `ssl.cert.extensions[].name` | str |
| `ssl.cert.fingerprint` | dict |
| `ssl.cert.fingerprint.sha1` | str |
| `ssl.cert.fingerprint.sha256` | str |
| `ssl.cert.issued` | str |
| `ssl.cert.issuer` | dict |
| `ssl.cert.issuer.C` | str |
| `ssl.cert.issuer.CN` | str |
| `ssl.cert.issuer.O` | str |
| `ssl.cert.pubkey` | dict |
| `ssl.cert.pubkey.bits` | int |
| `ssl.cert.pubkey.type` | str |
| `ssl.cert.serial` | int |
| `ssl.cert.sig_alg` | str |
| `ssl.cert.subject` | dict |
| `ssl.cert.subject.CN` | str |
| `ssl.cert.version` | int |
| `ssl.chain` | list |
| `ssl.chain_sha256` | list |
| `ssl.cipher` | dict |
| `ssl.cipher.bits` | int |
| `ssl.cipher.name` | str |
| `ssl.cipher.version` | str |
| `ssl.handshake_states` | list |
| `ssl.ja3s` | str |
| `ssl.jarm` | str |
| `ssl.ocsp` | dict |
| `ssl.tlsext` | list |
| `ssl.tlsext[].id` | int |
| `ssl.tlsext[].name` | str |
| `ssl.trust` | dict |
| `ssl.trust.browser` | NoneType |
| `ssl.trust.revoked` | bool |
| `ssl.versions` | list |
| `tags` | list |
| `timestamp` | str |
| `transport` | str |
| `version` | str |
