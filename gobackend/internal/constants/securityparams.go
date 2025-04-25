package constants

// Context Key Names
const (
	UserIDContextKey    = "user_id"
	UsernameContextKey  = "username"
	EmailContextKey     = "email"
	RequestIDContextKey = "request_id"
)

// Auth Token Types
const (
	TokenTypeAccess  = "access"
	TokenTypeRefresh = "refresh"
)

// Password Validation
const (
	MinPasswordLength = 8
	MinUsernameLength = 3
	MaxUsernameLength = 50
	MaxEmailLength    = 255
)

// GDPR Log Categories
const (
	GDPRCategoryStandard  = "standard"
	GDPRCategoryPersonal  = "personal"
	GDPRCategorySensitive = "sensitive"
)

// Pattern Types
const (
	PatternTypeAISearch      = "ai_search"
	PatternTypeNormal        = "normal"
	PatternTypeCaseSensitive = "case_sensitive"
)

// Detection Methods
const (
	DetectionMethodManual        = "Manual"
	DetectionMethodSearch        = "Search"
	DetectionMethodAiSearch      = "AiSearch"
	DetectionMethodCaseSensitive = "CaseSensitive"
	DetectionMethodMLModel1      = "Presidio"
	DetectionMethodMLModel2      = "Gliner"
	DetectionMethodAIModel       = "Gemini"
	DetectionMethodHideMeModel   = "HideMeModel"
)

// Theme Types
const (
	ThemeSystem = "system"
	ThemeLight  = "light"
	ThemeDark   = "dark"
)

// Cookie Names
const (
	RefreshTokenCookie = "refresh_token"
	AuthTokenCookie    = "auth_token"
	CSRFTokenCookie    = "csrf_token"
)

// Default Log Paths
const (
	DefaultStandardLogPath  = "./logs/standard"
	DefaultPersonalLogPath  = "./logs/personal"
	DefaultSensitiveLogPath = "./logs/sensitive"
)
