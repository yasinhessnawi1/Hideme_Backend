package models

// BanList represents a collection of words to exclude from detection.
// The ban list is associated with a specific user's settings.
type BanList struct {
	ID        int64 `json:"id" db:"ban_id"`
	SettingID int64 `json:"setting_id" db:"setting_id"`
}

// TableName returns the database table name for the BanList model.
func (bl *BanList) TableName() string {
	return "ban_lists"
}

// NewBanList creates a new BanList with the given setting ID.
func NewBanList(settingID int64) *BanList {
	return &BanList{
		SettingID: settingID,
	}
}

// BanListWithWords represents a ban list with its associated banned words.
// This is a convenience struct for API responses.
type BanListWithWords struct {
	ID    int64    `json:"id"`
	Words []string `json:"words"`
}
