// Package models provides data structures and operations for the HideMe application.
// This file contains models related to search patterns used for detecting
// sensitive information in documents through various search strategies.
package models

// PatternType defines the type of pattern for searching documents.
// Different pattern types enable various search strategies with different
// levels of sensitivity and precision for detecting information.
type PatternType string

// Available pattern types for searching documents.
// These constants define the supported search strategies within the application,
// each with different characteristics for sensitive information detection.
const (
	// AISearch represents an AI-powered search pattern that uses advanced
	// algorithms to identify sensitive information based on context and semantics.
	AISearch PatternType = "ai_search"

	// Normal represents a basic search pattern that performs standard
	// case-insensitive text matching for sensitive information.
	Normal PatternType = "normal"

	// CaseSensitive represents a case-sensitive search pattern that matches
	// text exactly as specified, including letter case.
	CaseSensitive PatternType = "case_sensitive"
)

// SearchPattern represents custom patterns defined by users for detecting
// sensitive information in documents. These patterns allow users to customize
// the detection process to their specific privacy requirements.
type SearchPattern struct {
	// ID is the unique identifier for this search pattern
	ID int64 `json:"id" db:"pattern_id"`

	// SettingID references the user settings to which this pattern belongs
	SettingID int64 `json:"setting_id" db:"setting_id"`

	// PatternType defines the search strategy to use for this pattern
	PatternType PatternType `json:"pattern_type" db:"pattern_type"`

	// PatternText contains the actual text or pattern to search for
	PatternText string `json:"pattern_text" db:"pattern_text"`
}

// TableName returns the database table name for the SearchPattern model.
// This method is used by ORM frameworks to determine where to persist this entity.
func (sp *SearchPattern) TableName() string {
	return "search_patterns"
}

// NewSearchPattern creates a new SearchPattern with the given parameters.
//
// Parameters:
//   - settingID: The ID of the user settings to which this pattern belongs
//   - patternType: The type of search to perform (AISearch, Normal, or CaseSensitive)
//   - patternText: The text or pattern to search for
//
// Returns:
//   - A new SearchPattern pointer with the specified parameters
//
// Custom search patterns allow users to define specific terms or patterns
// that should be detected and redacted in their documents.
func NewSearchPattern(settingID int64, patternType PatternType, patternText string) *SearchPattern {
	return &SearchPattern{
		SettingID:   settingID,
		PatternType: patternType,
		PatternText: patternText,
	}
}

// ValidatePatternType checks if the provided pattern type is valid.
//
// Parameters:
//   - patternType: The pattern type to validate
//
// Returns:
//   - true if the pattern type is valid (AISearch, Normal, or CaseSensitive), false otherwise
//
// This function ensures that only supported search strategies are used when
// creating or updating search patterns.
func ValidatePatternType(patternType PatternType) bool {
	return patternType == AISearch || patternType == Normal || patternType == CaseSensitive
}

// SearchPatternCreate represents a request to create a new search pattern.
// This structure validates input parameters for search pattern creation.
type SearchPatternCreate struct {
	// PatternType defines the search strategy to use
	// Must be one of: "ai_search", "normal", or "case_sensitive"
	PatternType string `json:"pattern_type" validate:"required,oneof=ai_search normal case_sensitive"`

	// PatternText contains the actual text or pattern to search for
	// Must be non-empty
	PatternText string `json:"pattern_text" validate:"required,min=1"`
}

// SearchPatternUpdate represents a request to update an existing search pattern.
// This structure validates input parameters for search pattern updates,
// allowing for partial updates where only some fields are modified.
type SearchPatternUpdate struct {
	// PatternType defines the search strategy to use
	// If provided, must be one of: "ai_search", "normal", or "case_sensitive"
	PatternType string `json:"pattern_type" validate:"omitempty,oneof=ai_search normal case_sensitive"`

	// PatternText contains the actual text or pattern to search for
	// If provided, must be non-empty
	PatternText string `json:"pattern_text" validate:"omitempty,min=1"`
}

// SearchPatternDelete represents a request to delete specific search patterns.
// This structure validates delete operations to ensure proper request format.
type SearchPatternDelete struct {
	// IDs contains the unique identifiers of the search patterns to delete
	// Must contain at least one valid ID
	IDs []int64 `json:"ids" validate:"required,min=1,dive,required,min=1"`
}
