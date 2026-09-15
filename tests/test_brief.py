from src.brief import evidence_ports
from src.scoring import Signal


def test_only_signal_bearing_ports_reach_the_brief():
    signals = (
        Signal(
            code="exposed_winrm",
            weight=30,
            detail="Public Windows remote-management service on port 5985",
        ),
        Signal(code="identified_cpe", weight=5, detail="Product identifier exposed"),
    )
    ports = [80, 443, 5985, 8080, 9000, 9001, 9002, 9003]

    cited, withheld = evidence_ports(ports, signals)

    assert cited == (5985,)
    assert withheld == 7


def test_status_codes_in_details_are_not_mistaken_for_ports():
    signals = (
        Signal(
            code="http_server_error",
            weight=10,
            detail="Public endpoint returned HTTP 502",
        ),
        Signal(
            code="exposed_winrm",
            weight=30,
            detail="Public Windows remote-management service on port 8080",
        ),
    )

    cited, withheld = evidence_ports([80, 502, 8080], signals)

    assert cited == (8080,)
    assert withheld == 2


def test_accounts_without_a_cited_port_still_show_some_surface():
    signals = (
        Signal(code="weak_tls", weight=20, detail="Expired certificate observed"),
    )

    cited, withheld = evidence_ports([443, 8443, 9443], signals, limit=2)

    assert cited == (443, 8443)
    assert withheld == 1


def test_short_port_lists_are_passed_through_whole():
    cited, withheld = evidence_ports([443, 80], ())

    assert cited == (80, 443)
    assert withheld == 0


def test_downranking_signals_do_not_promote_their_ports():
    signals = (
        Signal(code="cdn_edge", weight=-15, detail="CDN edge observed on port 443"),
    )

    cited, withheld = evidence_ports([22, 443], signals, limit=1)

    assert cited == (22,)
    assert withheld == 1
