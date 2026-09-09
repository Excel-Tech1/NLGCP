package ntrip

import (
	"regexp"
	"strings"
)

// Mountpoint admission and station-identity mapping (fail-closed). A
// mountpoint is not a station identity: ingestion requires an explicit
// mapping to a registry station, otherwise STATION_IDENTITY_UNVERIFIED
// gates Phase 8 correction-source use.

// AdmissionStatus is the mountpoint admission outcome.
type AdmissionStatus string

const (
	AdmissionAccept  AdmissionStatus = "ACCEPT"
	AdmissionWarn    AdmissionStatus = "WARN"
	AdmissionReject  AdmissionStatus = "REJECT"
	AdmissionBlocked AdmissionStatus = "BLOCKED"
)

// StationIdentityUnverified marks unmapped provider mountpoints.
const StationIdentityUnverified = "STATION_IDENTITY_UNVERIFIED"

// Admission is a mountpoint admission record.
type Admission struct {
	Provider                string
	CasterHost              string
	CasterPort              int
	Mountpoint              string
	StationMapping          string
	SourceTableFormat       string
	GNSSSystems             []string
	RequiresNMEA            bool
	AuthenticationMode      string
	ConfiguredAuthorization string
	Status                  AdmissionStatus
	ReasonCodes             []string
}

// StationMapping binds a provider mountpoint to a registry identity.
type StationMapping struct {
	Mountpoint string
	StationID  string
	Verified   bool
	Reason     string
}

// KnownStations mirrors the verified registry set shared with Phase 9.
var KnownStations = map[string]bool{
	"ABFC00NGA": true, "BKFP00NGA": true, "EKAK00NGA": true, "FUTY00NGA": true,
	"MGBO00NGA": true, "PHRI00NGA": true, "ULAG00NGA": true, "UNEC00NGA": true,
}

// MapStation maps a provider mountpoint onto a registry station identity.
func MapStation(mountpoint string, registry map[string]string) StationMapping {
	want := strings.ToUpper(strings.TrimPrefix(mountpoint, "/"))
	for rawMount, station := range registry {
		if strings.ToUpper(strings.TrimPrefix(rawMount, "/")) == want {
			if KnownStations[station] {
				return StationMapping{Mountpoint: mountpoint, StationID: station, Verified: true, Reason: "registry mapping to verified station"}
			}
			return StationMapping{Mountpoint: mountpoint, StationID: station, Verified: false, Reason: "registry station not in verified set: " + station}
		}
	}
	return StationMapping{Mountpoint: mountpoint, StationID: StationIdentityUnverified, Verified: false, Reason: "no registry mapping for mountpoint"}
}

// AdmitMountpoint creates the admission record before any ingestion.
func AdmitMountpoint(provider string, cfg Config, sourceTableFormat string, gnssSystems []string, requiresNMEA, needsAuth bool, mapping StationMapping) Admission {
	var reasons []string
	if cfg.Host == "" {
		reasons = append(reasons, "CONFIG_INVALID: empty caster host")
	}
	if cfg.Mountpoint == "" {
		reasons = append(reasons, "CONFIG_INVALID: empty mountpoint")
	}
	if needsAuth && cfg.Username == "" {
		reasons = append(reasons, "AUTH_REQUIRED: stream requires authentication, no username configured")
	}
	if requiresNMEA && cfg.GGASentence == "" {
		reasons = append(reasons, "NMEA_POSITION_REQUIRED: stream requires GGA, none configured")
	}
	if !mapping.Verified {
		reasons = append(reasons, "STATION_IDENTITY_UNVERIFIED: "+mapping.Reason)
	}
	if requiresNMEA {
		reasons = append(reasons, "WARN: stream requires periodic rover GGA")
	}
	if cfg.AllowInsecureTLS {
		reasons = append(reasons, "WARN: insecure TLS explicitly enabled (diagnostic only, unsafe)")
	}
	var blocking []string
	for _, reason := range reasons {
		if !strings.HasPrefix(reason, "WARN") {
			blocking = append(blocking, reason)
		}
	}
	status := AdmissionAccept
	if len(reasons) > 0 {
		status = AdmissionWarn
	}
	if len(blocking) > 0 {
		configBlocked := false
		for _, reason := range blocking {
			if strings.HasPrefix(reason, "CONFIG_INVALID") || strings.HasPrefix(reason, "AUTH_REQUIRED") || strings.Contains(reason, "NMEA_POSITION_REQUIRED") {
				configBlocked = true
			}
		}
		if configBlocked {
			status = AdmissionBlocked
		} else if containsReason(blocking, "STATION_IDENTITY_UNVERIFIED") {
			status = AdmissionWarn
		} else {
			status = AdmissionReject
		}
	}
	authMode := "none"
	if cfg.Username != "" {
		authMode = "basic"
	}
	configured := "anonymous"
	if cfg.Username != "" {
		configured = "configured"
	}
	return Admission{
		Provider: provider, CasterHost: cfg.Host, CasterPort: cfg.Port,
		Mountpoint: cfg.Mountpoint, StationMapping: mapping.StationID,
		SourceTableFormat: sourceTableFormat, GNSSSystems: gnssSystems,
		RequiresNMEA: requiresNMEA, AuthenticationMode: authMode,
		ConfiguredAuthorization: configured, Status: status, ReasonCodes: reasons,
	}
}

func containsReason(reasons []string, needle string) bool {
	for _, reason := range reasons {
		if strings.Contains(reason, needle) {
			return true
		}
	}
	return false
}

var unsafePathChars = regexp.MustCompile(`[^A-Za-z0-9._-]+`)

// SanitizeIdentifier maps untrusted provider/mountpoint strings onto a
// single safe path component; the original value stays in metadata.
func SanitizeIdentifier(value, fallback string) string {
	cleaned := unsafePathChars.ReplaceAllString(strings.TrimLeft(strings.TrimSpace(value), "/"), "_")
	cleaned = strings.Trim(cleaned, "._")
	if cleaned == "" || cleaned == "." || cleaned == ".." {
		return fallback
	}
	if len(cleaned) > 64 {
		cleaned = cleaned[:64]
	}
	return cleaned
}
