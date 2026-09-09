package ntrip

import (
	"strings"
)

// Source-table record kinds: STR (stream), CAS (caster), NET (network).
// Coordinates are provider metadata, never verified station coordinates.

// StrEntry is one parsed STR (stream) record.
type StrEntry struct {
	Mountpoint     string
	Identifier     string
	Format         string
	FormatDetails  string
	Carrier        string
	NavSystems     string
	Network        string
	Country        string
	Latitude       string
	Longitude      string
	NMEARequired   string
	Solution       string
	Generator      string
	ComprEncryp    string
	Authentication string
	Fee            string
	Bitrate        string
	Misc           string
}

// CasEntry is one parsed CAS (caster) record.
type CasEntry struct {
	Host, Port, Identifier, Operator, NMEA, Country, Latitude, Longitude, Misc string
}

// NetEntry is one parsed NET (network) record.
type NetEntry struct {
	Identifier, Operator, Authentication, Fee, WebNet, WebStr, WebReg, Misc string
}

// SourceTable is a parsed, bounded source-table body.
type SourceTable struct {
	Streams    []StrEntry
	Casters    []CasEntry
	Networks   []NetEntry
	Terminated bool
	Findings   []string
	SHA256     string
}

// ParseSourcetable parses a source-table body with explicit size/entry bounds.
func ParseSourcetable(text string, maxBytes, maxEntries int) SourceTable {
	raw := []byte(text)
	table := SourceTable{}
	if len(raw) > maxBytes {
		table.Findings = append(table.Findings, "SOURCETABLE_TOO_LARGE")
		raw = raw[:maxBytes]
		text = string(raw)
	}
	table.SHA256 = SHA256Hex(raw)
	count := 0
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimRight(strings.TrimSpace(line), "\r")
		if line == "" {
			continue
		}
		if line == "ENDSOURCETABLE" {
			table.Terminated = true
			continue
		}
		count++
		if count > maxEntries {
			table.Findings = append(table.Findings, "ENTRY_LIMIT")
			break
		}
		switch {
		case strings.HasPrefix(line, "STR;"):
			table.Streams = append(table.Streams, parseSTR(line))
		case strings.HasPrefix(line, "CAS;"):
			table.Casters = append(table.Casters, parseCAS(line))
		case strings.HasPrefix(line, "NET;"):
			table.Networks = append(table.Networks, parseNET(line))
		default:
			prefix := line
			if len(prefix) > 8 {
				prefix = prefix[:8]
			}
			table.Findings = append(table.Findings, "UNKNOWN_RECORD prefix="+prefix)
		}
	}
	if !table.Terminated {
		table.Findings = append(table.Findings, "MISSING_ENDSOURCETABLE")
	}
	return table
}

func splitFields(line string, width int) []string {
	fields := strings.Split(line, ";")[1:]
	for len(fields) < width {
		fields = append(fields, "")
	}
	return fields
}

func parseSTR(line string) StrEntry {
	f := splitFields(line, 18)
	return StrEntry{
		Mountpoint: f[0], Identifier: f[1], Format: f[2], FormatDetails: f[3],
		Carrier: f[4], NavSystems: f[5], Network: f[6], Country: f[7],
		Latitude: f[8], Longitude: f[9], NMEARequired: f[10], Solution: f[11],
		Generator: f[12], ComprEncryp: f[13], Authentication: f[14], Fee: f[15],
		Bitrate: f[16], Misc: f[17],
	}
}

func parseCAS(line string) CasEntry {
	f := splitFields(line, 9)
	return CasEntry{
		Host: f[0], Port: f[1], Identifier: f[2], Operator: f[3], NMEA: f[4],
		Country: f[5], Latitude: f[6], Longitude: f[7], Misc: f[8],
	}
}

func parseNET(line string) NetEntry {
	f := splitFields(line, 8)
	return NetEntry{
		Identifier: f[0], Operator: f[1], Authentication: f[2], Fee: f[3],
		WebNet: f[4], WebStr: f[5], WebReg: f[6], Misc: f[7],
	}
}

// FindStream locates a stream by mountpoint (case-insensitive, slash-tolerant).
func FindStream(table SourceTable, mountpoint string) *StrEntry {
	want := strings.ToUpper(strings.TrimPrefix(mountpoint, "/"))
	for i := range table.Streams {
		if strings.ToUpper(strings.TrimPrefix(table.Streams[i].Mountpoint, "/")) == want {
			return &table.Streams[i]
		}
	}
	return nil
}

// StreamRequiresNMEA reports whether the stream demands rover GGA.
func StreamRequiresNMEA(entry *StrEntry) bool {
	return entry != nil && strings.TrimSpace(entry.NMEARequired) == "1"
}

// StreamNeedsAuth reports whether the stream requires authentication.
func StreamNeedsAuth(entry *StrEntry) bool {
	if entry == nil {
		return false
	}
	switch strings.ToUpper(strings.TrimSpace(entry.Authentication)) {
	case "B", "D", "Y", "1":
		return true
	default:
		return false
	}
}
