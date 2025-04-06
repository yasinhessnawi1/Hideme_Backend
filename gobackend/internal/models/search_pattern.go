package models

// PatternType defines the type of pattern for searching documents.
type PatternType string

// Available pattern types
const (
	// AISearch represents an AI-powered search pattern
	AISearch PatternType = "ai_search"
	// Normal represents a basic search pattern
	Normal PatternType = "normal"
	// CaseSensitive represents a case-sensitive search pattern
	CaseSensitive PatternType = "case_sensitive"
)

// SearchPattern represents custom patterns defined by users for detecting
// sensitive information in documents.
type SearchPattern struct {
	ID          int64       `json:"id" db:"pattern_id"`
	SettingID   int64       `json:"setting_id" db:"setting_id"`
	PatternType PatternType `json:"pattern_type" db:"pattern_type"`
	PatternText string      `json:"pattern_text" db:"pattern_text"`
}

// TableName returns the database table name for the SearchPattern model.
func (sp *SearchPattern) TableName() string {
	return "search_patterns"
}

// NewSearchPattern creates a new SearchPattern with the given parameters.
func NewSearchPattern(settingID int64, patternType PatternType, patternText string) *SearchPattern {
	return &SearchPattern{
		SettingID:   settingID,
		PatternType: patternType,
		PatternText: patternText,
	}
}

// ValidatePatternType checks if the provided pattern type is valid.
func ValidatePatternType(patternType PatternType) bool {
	return patternType == AISearch || patternType == Normal || patternType == CaseSensitive
}

// SearchPatternCreate represents a request to create a new search pattern.
type SearchPatternCreate struct {
	PatternType string `json:"pattern_type" validate:"required,oneof=ai_search normal case_sensitive"`
	PatternText string `json:"pattern_text" validate:"required,min=1"`
}

// SearchPatternUpdate represents a request to update an existing search pattern.
type SearchPatternUpdate struct {
	PatternType string `json:"pattern_type" validate:"omitempty,oneof=ai_search normal case_sensitive"`
	PatternText string `json:"pattern_text" validate:"omitempty,min=1"`
}

// SearchPatternDelete represents a request to delete specific search patterns.
type SearchPatternDelete struct {
	IDs []int64 `json:"ids" validate:"required,min=1,dive,required,min=1"`
}
