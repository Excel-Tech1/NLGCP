package ntrip

import (
	"fmt"
	"strings"
)

// Live delivery subjects mirror the reserved correction.* family:
// live ingestion publishes under correction.live.<STATION> while the
// Phase 9 replay path uses correction.replay.<STATION>, so one consumer
// contract covers both origins. Names only; no transport is opened here.
const (
	SubjectFamily      = "correction"
	LiveSubjectPrefix  = "correction.live"
	ReplaySubjectPrime = "correction.replay"
)

// LiveSubject returns the delivery subject for one station.
func LiveSubject(stationID string) (string, error) {
	station := strings.ToUpper(strings.TrimSpace(stationID))
	if station == "" {
		return "", &ConfigError{Field: "station_id"}
	}
	for _, r := range station {
		if !(r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || r == '-' || r == '_') {
			return "", fmt.Errorf("unsafe station_id for subject: %q", stationID)
		}
	}
	return LiveSubjectPrefix + "." + station, nil
}
