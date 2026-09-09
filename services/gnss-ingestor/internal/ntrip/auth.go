package ntrip

import (
	"encoding/base64"
	"regexp"
	"strings"
)

// Redacted is the placeholder substituted for every secret.
const Redacted = "***REDACTED***"

var (
	urlCreds     = regexp.MustCompile(`://[^/@\s]*@`)
	passwordKV   = regexp.MustCompile(`(?i)(password\s*[:=]\s*)\S+`)
	sensitiveKey = regexp.MustCompile(`(?i)password|passwd|pwd|secret|token`)
)

// BasicAuthHeader builds an NTRIP Basic authorization header value.
func BasicAuthHeader(username, password string) string {
	raw := username + ":" + password
	return "Basic " + base64.StdEncoding.EncodeToString([]byte(raw))
}

// RedactURL removes user:pass credentials embedded in a URL.
func RedactURL(url string) string {
	return urlCreds.ReplaceAllString(url, "://"+Redacted+"@")
}

// RedactText replaces known secret values (plus password:= assignments)
// in free text so passwords never reach logs.
func RedactText(text string, secrets []string) string {
	redacted := text
	for _, secret := range secrets {
		if secret != "" {
			redacted = strings.ReplaceAll(redacted, secret, Redacted)
		}
	}
	return passwordKV.ReplaceAllString(redacted, "${1}"+Redacted)
}

// RedactHeaders redacts authorization headers and embedded secrets.
func RedactHeaders(headers map[string]string, secrets []string) map[string]string {
	out := make(map[string]string, len(headers))
	for key, value := range headers {
		if strings.EqualFold(key, "authorization") || strings.EqualFold(key, "proxy-authorization") {
			out[key] = Redacted
			continue
		}
		out[key] = RedactText(value, secrets)
	}
	return out
}

// IsSensitiveKey reports whether a config key holds secret material.
func IsSensitiveKey(key string) bool { return sensitiveKey.MatchString(key) }

// SanitizeMapping copies a string mapping while redacting secrets.
func SanitizeMapping(payload map[string]string) map[string]string {
	out := make(map[string]string, len(payload))
	for key, value := range payload {
		if IsSensitiveKey(key) {
			out[key] = Redacted
			continue
		}
		out[key] = value
	}
	return out
}
