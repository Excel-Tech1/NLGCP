package ntrip

import (
	"bytes"
	"strings"
	"testing"
	"time"
)

const testSourceTable = "CAS;127.0.0.1;2101;TEST-CASTER;Op;0;NGA;0.0;0.0;T\r\n" +
	"NET;TEST-NET;Op;B;N;http://example.invalid;http://example.invalid;;\r\n" +
	"STR;TEST00SYN;Test Station;RTCM 3.2;1005(1),1077(1);2;GPS+GLO;TEST-NET;NGA;6.45;3.39;1;0;Gen;None;B;N;9600;\r\n" +
	"STR;OPEN00SYN;Open Station;RTCM 3.2;1005(1);2;GPS;TEST-NET;NGA;6.45;3.39;0;0;Gen;None;N;N;9600;\r\n" +
	"ENDSOURCETABLE\r\n"

func TestParseSourcetable(t *testing.T) {
	table := ParseSourcetable(testSourceTable, 65536, 10000)
	if !table.Terminated || len(table.Streams) != 2 || len(table.Casters) != 1 || len(table.Networks) != 1 {
		t.Fatalf("table = %+v", table)
	}
	if len(table.Findings) != 0 {
		t.Fatalf("findings = %v", table.Findings)
	}
	if table.Streams[0].Mountpoint != "TEST00SYN" || table.Streams[0].Country != "NGA" {
		t.Fatalf("stream = %+v", table.Streams[0])
	}
}

func TestSourcetableStreamFlags(t *testing.T) {
	table := ParseSourcetable(testSourceTable, 65536, 10000)
	locked := FindStream(table, "TEST00SYN")
	open := FindStream(table, "/open00syn")
	if locked == nil || open == nil {
		t.Fatal("streams not found")
	}
	if !StreamNeedsAuth(locked) || !StreamRequiresNMEA(locked) {
		t.Fatalf("locked = %+v", locked)
	}
	if StreamNeedsAuth(open) || StreamRequiresNMEA(open) {
		t.Fatalf("open = %+v", open)
	}
	if FindStream(table, "MISSING") != nil {
		t.Fatal("missing stream must be nil")
	}
}

func TestSourcetableSafetyLimits(t *testing.T) {
	big := strings.Repeat("STR;"+strings.Repeat("X", 100)+"\r\n", 100) + "ENDSOURCETABLE\r\n"
	table := ParseSourcetable(big, 500, 10000)
	found := false
	for _, finding := range table.Findings {
		found = found || strings.Contains(finding, "SOURCETABLE_TOO_LARGE")
	}
	if !found {
		t.Fatalf("findings = %v", table.Findings)
	}
	many := ""
	for i := range 50 {
		many += "STR;M" + string(rune('0'+i%10)) + ";id\r\n"
	}
	many += "ENDSOURCETABLE\r\n"
	table = ParseSourcetable(many, 65536, 10)
	if len(table.Streams) != 10 {
		t.Fatalf("streams = %d", len(table.Streams))
	}
	bare := ParseSourcetable("STR;A;B\r\n", 65536, 10000)
	if bare.Terminated {
		t.Fatal("missing terminator must be recorded")
	}
}

func TestHandshakeValidation(t *testing.T) {
	if result := ValidateStreamResponse("HTTP/1.1 200 OK", nil, []byte{0xD3, 0x00}); !result.OK {
		t.Fatalf("v2 200 = %+v", result)
	}
	if result := ValidateStreamResponse("ICY 200 OK", nil, []byte{0xD3}); !result.OK {
		t.Fatalf("v1 ICY = %+v", result)
	}
	cases := []struct {
		line string
		body []byte
		want FailureClass
	}{
		{"HTTP/1.1 401 Unauthorized", nil, FailureAuth},
		{"HTTP/1.1 403 Forbidden", nil, FailureForbidden},
		{"HTTP/1.1 404 Not Found", nil, FailureNotFound},
		{"HTTP/1.1 200 OK", []byte("<html>oops</html>"), FailureWrongContent},
		{"HTTP/1.1 200 OK", []byte("STR;A;B\r\nENDSOURCETABLE\r\n"), FailureWrongContent},
		{"", nil, FailureEmpty},
		{"GARBAGE-NO-CODE", nil, FailureProtocol},
		{"HTTP/1.1 500 Error", nil, FailureProtocol},
	}
	for _, tc := range cases {
		if result := ValidateStreamResponse(tc.line, nil, tc.body); result.OK || result.Failure != tc.want {
			t.Fatalf("line %q = %+v, want %s", tc.line, result, tc.want)
		}
	}
}

func TestTerminalClassification(t *testing.T) {
	for _, failure := range []FailureClass{FailureAuth, FailureNotFound, FailureForbidden, FailureConfig} {
		if !IsTerminal(failure) {
			t.Fatalf("%s must be terminal", failure)
		}
	}
	for _, failure := range []FailureClass{FailureTimeout, FailureStalled, FailureLost, FailureProtocol} {
		if IsTerminal(failure) {
			t.Fatalf("%s must be transient", failure)
		}
	}
	if ClassifyStatusCode(401) != FailureAuth || ClassifyStatusCode(404) != FailureNotFound {
		t.Fatal("status classification wrong")
	}
}

func TestReconnectSchedule(t *testing.T) {
	policy := DefaultReconnectPolicy()
	if policy.DelayForAttempt(1, nil) != 1 || policy.DelayForAttempt(2, nil) != 2 || policy.DelayForAttempt(3, nil) != 4 {
		t.Fatalf("schedule = %v %v %v", policy.DelayForAttempt(1, nil), policy.DelayForAttempt(2, nil), policy.DelayForAttempt(3, nil))
	}
	if policy.DelayForAttempt(100, nil) != 30 {
		t.Fatal("cap not applied")
	}
	if !policy.Exhausted(8) || policy.Exhausted(7) {
		t.Fatal("exhaustion wrong")
	}
	if len(policy.Validate()) != 0 {
		t.Fatal("default policy must validate")
	}
	seed := int64(7)
	if policy.DelayForAttempt(2, &seed) != policy.DelayForAttempt(2, &seed) {
		t.Fatal("seeded jitter must be deterministic")
	}
	bad := ReconnectPolicy{BaseDelayS: 0, MaxDelayS: 0, MaxAttempts: -1}
	if len(bad.Validate()) == 0 {
		t.Fatal("bad policy must not validate")
	}
}

func TestConfigEnvAndValidation(t *testing.T) {
	t.Setenv(EnvHost, "caster.example.invalid")
	t.Setenv(EnvPort, "2102")
	t.Setenv(EnvMount, "TEST00SYN")
	t.Setenv(EnvUser, "user")
	t.Setenv(EnvPassword, "pw")
	t.Setenv(EnvTLS, "true")
	cfg := ConfigFromEnv()
	if cfg.Host != "caster.example.invalid" || cfg.Port != 2102 || !cfg.UseTLS {
		t.Fatalf("cfg = %+v", cfg)
	}
	if len(cfg.Validate()) != 0 {
		t.Fatalf("validate = %v", cfg.Validate())
	}
	snapshot := cfg.RedactedSnapshot()
	if snapshot["password"] != Redacted || strings.Contains(snapshot["password"], "pw") {
		t.Fatalf("snapshot = %v", snapshot)
	}
	empty := DefaultConfig()
	if len(empty.Validate()) == 0 {
		t.Fatal("empty host must not validate")
	}
}

func TestStreamRequestFormation(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Host = "caster.example.invalid"
	cfg.Mountpoint = "TEST00SYN"
	cfg.Username = "user"
	cfg.Password = "pw"
	request := string(BuildStreamRequest(cfg))
	if !strings.HasPrefix(request, "GET /TEST00SYN HTTP/1.1") {
		t.Fatalf("request = %q", request)
	}
	if !strings.Contains(request, "Ntrip-Version: Ntrip/2.0") || !strings.Contains(request, "Authorization: Basic ") {
		t.Fatalf("request = %q", request)
	}
	plain := DefaultConfig()
	plain.Host = "caster.example.invalid"
	plain.Mountpoint = "/TEST00SYN"
	if strings.Contains(string(BuildStreamRequest(plain)), "Authorization:") {
		t.Fatal("anonymous request must not carry auth")
	}
	if !strings.HasPrefix(string(BuildSourcetableRequest(cfg)), "GET / HTTP/1.1") {
		t.Fatal("source-table request must target /")
	}
}

func TestAdmissionAndMapping(t *testing.T) {
	cfg := DefaultConfig()
	cfg.Host = "caster.example.invalid"
	cfg.Mountpoint = "OPEN00SYN"
	mapping := MapStation("OPEN00SYN", map[string]string{"OPEN00SYN": "EKAK00NGA"})
	if !mapping.Verified || mapping.StationID != "EKAK00NGA" {
		t.Fatalf("mapping = %+v", mapping)
	}
	admission := AdmitMountpoint("test", cfg, "RTCM 3.2", []string{"GPS"}, false, false, mapping)
	if admission.Status != AdmissionAccept {
		t.Fatalf("admission = %+v", admission)
	}
	unmapped := MapStation("MYSTERY", nil)
	if unmapped.Verified || unmapped.StationID != StationIdentityUnverified {
		t.Fatalf("mapping = %+v", unmapped)
	}
	warn := AdmitMountpoint("test", cfg, "RTCM 3.2", []string{"GPS"}, false, false, unmapped)
	if warn.Status != AdmissionWarn {
		t.Fatalf("admission = %+v", warn)
	}
	needsGGA := AdmitMountpoint("test", cfg, "RTCM 3.2", []string{"GPS"}, true, false, mapping)
	if needsGGA.Status != AdmissionBlocked {
		t.Fatalf("admission = %+v", needsGGA)
	}
	needsAuth := AdmitMountpoint("test", cfg, "RTCM 3.2", []string{"GPS"}, false, true, mapping)
	if needsAuth.Status != AdmissionBlocked {
		t.Fatalf("admission = %+v", needsAuth)
	}
	badHost := cfg
	badHost.Host = ""
	if AdmitMountpoint("test", badHost, "RTCM 3.2", nil, false, false, mapping).Status != AdmissionBlocked {
		t.Fatal("empty host must block")
	}
}

func TestSanitizeIdentifier(t *testing.T) {
	if SanitizeIdentifier("../../etc", "unknown") != "etc" {
		t.Fatal("traversal not sanitized")
	}
	if SanitizeIdentifier("", "unknown") != "unknown" || SanitizeIdentifier("..", "unknown") != "unknown" {
		t.Fatal("fallback wrong")
	}
	if SanitizeIdentifier("TEST00SYN", "unknown") != "TEST00SYN" {
		t.Fatal("valid identifier mangled")
	}
}

func TestBoundedBuffer(t *testing.T) {
	buffer, err := NewBoundedBuffer[int](1, BlockBackpressure)
	if err != nil {
		t.Fatal(err)
	}
	if !buffer.TryPut(1) || buffer.TryPut(2) {
		t.Fatal("block policy must refuse when full")
	}
	if buffer.Waits != 1 {
		t.Fatalf("waits = %d", buffer.Waits)
	}
	if item, ok := buffer.Take(); !ok || item != 1 {
		t.Fatalf("take = %v %v", item, ok)
	}
	buffer.ForcePut(2)
	if buffer.HighWater != 1 || buffer.Occupancy() != 1 {
		t.Fatalf("buffer = %+v", buffer)
	}
	dropper, _ := NewBoundedBuffer[int](1, DropNewestExplicit)
	_ = dropper.TryPut(1)
	if dropper.TryPut(2) || dropper.Dropped != 1 {
		t.Fatalf("dropper = %+v", dropper)
	}
	if _, err := NewBoundedBuffer[int](0, BlockBackpressure); err == nil {
		t.Fatal("capacity 0 must fail")
	}
}

func TestIdleTracker(t *testing.T) {
	now := time.Now()
	clock := now
	tracker := NewIdleTracker(100*time.Millisecond, func() time.Time { return clock })
	if tracker.Stalled() {
		t.Fatal("fresh tracker must not stall")
	}
	clock = clock.Add(250 * time.Millisecond)
	if !tracker.Stalled() || tracker.Events != 1 {
		t.Fatal("stall not detected")
	}
	tracker.NoteBytes()
	if tracker.Stalled() {
		t.Fatal("activity must clear stall")
	}
}

func TestLiveSubject(t *testing.T) {
	subject, err := LiveSubject("EKAK00NGA")
	if err != nil || subject != "correction.live.EKAK00NGA" {
		t.Fatalf("subject = %q %v", subject, err)
	}
	if _, err := LiveSubject("../../evil"); err == nil {
		t.Fatal("unsafe station must fail")
	}
	if _, err := LiveSubject(""); err == nil {
		t.Fatal("empty station must fail")
	}
}

func TestSplitHead(t *testing.T) {
	head, rest, ok := SplitHead([]byte("HTTP/1.1 200 OK\r\nA: b\r\n\r\nPAY"), 8192)
	if !ok || string(rest) != "PAY" {
		t.Fatalf("split = %q %v", rest, ok)
	}
	status, headers := ParseHead(head)
	if status != "HTTP/1.1 200 OK" || headers["A"] != "b" {
		t.Fatalf("head = %q %v", status, headers)
	}
	if _, _, ok := SplitHead([]byte("partial"), 8192); ok {
		t.Fatal("partial head must not split")
	}
	if _, _, ok := SplitHead(bytes.Repeat([]byte("x"), 9000), 8192); ok {
		t.Fatal("oversize head must not split")
	}
}
