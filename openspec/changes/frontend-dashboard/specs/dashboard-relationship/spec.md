# Dashboard Relationship

Relationship butler domain views in the dashboard. Provides read-only API endpoints for browsing contacts, groups, labels, and all related entities (notes, interactions, gifts, loans, important dates, quick facts, relationships, activity feed) from the Relationship butler's dedicated `butler_relationship` database. The frontend renders a contacts table, contact detail page, and groups page.

All data is read directly from the Relationship butler's database via the dual data-access pattern (D1). No write operations are exposed from the dashboard -- the Relationship butler's MCP tools are the sole write path.

The Relationship butler's schema includes: `contacts`, `contact_info`, `relationships`, `important_dates`, `notes`, `interactions`, `gifts`, `loans`, `groups`, `group_members`, `labels`, `contact_labels`, `quick_facts`, `addresses`, and `contact_feed`. See the `butler-relationship` spec for the full schema definition.

## ADDED Requirements

### Requirement: List and search contacts API

The dashboard API SHALL expose `GET /api/butlers/relationship/contacts` which returns a paginated, searchable, filterable list of contacts from the Relationship butler's `contacts` table via a direct database read. Only contacts with `listed=true` SHALL be returned.

The endpoint SHALL accept the following query parameters:
- `q` (string, optional) -- search term matched case-insensitively against `first_name`, `last_name`, `nickname`, and `company` using partial matching (SQL `ILIKE '%' || q || '%'`)
- `label` (string, optional) -- filter to contacts that have a label whose `name` matches this value exactly, joined through `contact_labels` and `labels`
- `limit` (integer, optional, default 20) -- maximum number of contacts to return
- `offset` (integer, optional, default 0) -- number of contacts to skip for pagination

Each contact object in the response MUST include:
- `id` (UUID) -- the contact's primary key
- `first_name` (string or null)
- `last_name` (string or null)
- `company` (string or null)
- `labels` (array of objects) -- each containing `id`, `name`, and `color`, joined from `contact_labels` and `labels`
- `last_interaction_at` (ISO 8601 timestamp or null) -- the `occurred_at` of the most recent row in the `interactions` table for this contact, or null if no interactions exist

The response MUST include a `total` field indicating the total count of contacts matching the filters (before pagination), to support frontend pagination controls.

The results SHALL be ordered by `last_name` ascending, then `first_name` ascending by default.

#### Scenario: Fetch all contacts with default pagination

- **WHEN** `GET /api/butlers/relationship/contacts` is called with no query parameters
- **THEN** the API MUST query the Relationship butler's database and return at most 20 listed contacts ordered by `last_name` ascending, then `first_name` ascending
- **AND** each contact object MUST include `id`, `first_name`, `last_name`, `company`, `labels` (array), and `last_interaction_at`
- **AND** the response MUST include a `total` field with the count of all listed contacts
- **AND** the response status MUST be 200

#### Scenario: Search contacts by name

- **WHEN** `GET /api/butlers/relationship/contacts?q=alice` is called
- **THEN** the API MUST return only listed contacts where `first_name`, `last_name`, `nickname`, or `company` contains `"alice"` (case-insensitive)
- **AND** the `total` field MUST reflect the count of matching contacts

#### Scenario: Search contacts by company

- **WHEN** `GET /api/butlers/relationship/contacts?q=acme` is called and a contact has `company='Acme Corp'`
- **THEN** that contact MUST be included in the results

#### Scenario: Filter contacts by label

- **WHEN** `GET /api/butlers/relationship/contacts?label=VIP` is called
- **THEN** the API MUST return only listed contacts that have a label with `name='VIP'` assigned via the `contact_labels` join table
- **AND** contacts without the `"VIP"` label MUST NOT be included

#### Scenario: Combine search and label filter

- **WHEN** `GET /api/butlers/relationship/contacts?q=smith&label=VIP` is called
- **THEN** the API MUST return only listed contacts whose name or company matches `"smith"` AND who have the `"VIP"` label assigned
- **AND** the `total` field MUST reflect the count of contacts matching both filters

#### Scenario: Paginate through contacts

- **WHEN** `GET /api/butlers/relationship/contacts?limit=10&offset=20` is called
- **THEN** the API MUST skip the first 20 matching contacts and return at most 10

#### Scenario: No contacts match the search

- **WHEN** `GET /api/butlers/relationship/contacts?q=zzzznonexistent` is called and no contacts match
- **THEN** the API MUST return an empty list with `total` set to `0`
- **AND** the response status MUST be 200

#### Scenario: Last interaction date is populated from interactions table

- **WHEN** a contact has 3 interactions with `occurred_at` values of `2026-01-01`, `2026-02-05`, and `2026-01-15`
- **THEN** that contact's `last_interaction_at` in the response MUST be `2026-02-05` (the most recent)

#### Scenario: Contact with no interactions has null last_interaction_at

- **WHEN** a contact has no rows in the `interactions` table
- **THEN** that contact's `last_interaction_at` MUST be `null`

#### Scenario: Archived contacts are excluded

- **WHEN** a contact has `listed=false`
- **THEN** that contact MUST NOT appear in the results regardless of search or filter parameters

---

### Requirement: Contact detail API

The dashboard API SHALL expose `GET /api/butlers/relationship/contacts/:id` which returns a single contact's full record with joined data from related tables via a direct database read.

The response MUST include:
- All columns from the `contacts` table (`id`, `first_name`, `last_name`, `nickname`, `company`, `job_title`, `gender`, `pronouns`, `avatar_url`, `listed`, `metadata`, `created_at`, `updated_at`)
- `info` (array) -- all rows from `contact_info` for this contact, each containing `id`, `type`, `value`, `label`, `created_at`
- `addresses` (array) -- all rows from `addresses` for this contact, each containing `id`, `type`, `line_1`, `line_2`, `city`, `province`, `postal_code`, `country`, `is_current`, `created_at`
- `important_dates` (array) -- all rows from `important_dates` for this contact, each containing `id`, `label`, `day`, `month`, `year`, `created_at`
- `quick_facts` (array) -- all rows from `quick_facts` for this contact, each containing `id`, `category`, `content`, `created_at`
- `relationships` (array) -- all rows from `relationships` where `contact_id` matches, each containing `id`, `related_contact_id`, `group_type`, `type`, `reverse_type`, `created_at`, and a nested `related_contact` object with `id`, `first_name`, `last_name`, `company`
- `labels` (array) -- all labels assigned to this contact via `contact_labels`, each containing `id`, `name`, `color`

#### Scenario: Fetch an existing contact with full detail

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid` is called and the contact exists
- **THEN** the API MUST return the complete contact record with all joined data
- **AND** the `info` array MUST contain all `contact_info` rows for that contact
- **AND** the `addresses` array MUST contain all address rows for that contact
- **AND** the `important_dates` array MUST contain all important date rows for that contact
- **AND** the `quick_facts` array MUST contain all quick fact rows for that contact
- **AND** the `relationships` array MUST contain all relationship rows where this contact is the `contact_id`, each including the related contact's name
- **AND** the `labels` array MUST contain all labels assigned to this contact
- **AND** the response status MUST be 200

#### Scenario: Contact does not exist

- **WHEN** `GET /api/butlers/relationship/contacts/nonexistent-uuid` is called and no contact with that ID exists
- **THEN** the API MUST return a 404 response with an error message indicating the contact was not found

#### Scenario: Contact with no related data

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid` is called for a contact that has no contact_info, addresses, important_dates, quick_facts, relationships, or labels
- **THEN** the API MUST return the contact record with all joined arrays as empty arrays (`[]`)
- **AND** the response status MUST be 200

#### Scenario: Relationships include related contact details

- **WHEN** a contact has a relationship of type `"parent"` with another contact named "Bob Smith" at "Acme Corp"
- **THEN** the relationship entry in the `relationships` array MUST include a `related_contact` object with `id`, `first_name` set to `"Bob"`, `last_name` set to `"Smith"`, and `company` set to `"Acme Corp"`

---

### Requirement: Contact activity feed API

The dashboard API SHALL expose `GET /api/butlers/relationship/contacts/:id/feed` which returns the activity feed for a specific contact from the `contact_feed` table via a direct database read.

The endpoint SHALL accept the following query parameters:
- `limit` (integer, optional, default 50) -- maximum number of feed entries to return
- `offset` (integer, optional, default 0) -- number of entries to skip for pagination

The results SHALL be ordered by `created_at` descending. Each feed entry MUST include `id`, `contact_id`, `action`, `entity_type`, `entity_id`, `summary`, and `created_at`.

#### Scenario: Fetch activity feed for a contact

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/feed` is called and the contact has 10 feed entries
- **THEN** the API MUST return all 10 entries ordered by `created_at` descending
- **AND** each entry MUST include `id`, `contact_id`, `action`, `entity_type`, `entity_id`, `summary`, and `created_at`
- **AND** the response status MUST be 200

#### Scenario: Paginate through feed entries

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/feed?limit=10&offset=10` is called and the contact has 25 feed entries
- **THEN** the API MUST return at most 10 entries, skipping the first 10 (by `created_at` descending)

#### Scenario: Contact has no feed entries

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/feed` is called and the contact has no entries in the `contact_feed` table
- **THEN** the API MUST return an empty list
- **AND** the response status MUST be 200

#### Scenario: Contact does not exist

- **WHEN** `GET /api/butlers/relationship/contacts/nonexistent-uuid/feed` is called and no contact with that ID exists
- **THEN** the API MUST return a 404 response with an error message indicating the contact was not found

---

### Requirement: Contact notes API

The dashboard API SHALL expose `GET /api/butlers/relationship/contacts/:id/notes` which returns notes for a specific contact from the `notes` table via a direct database read.

The endpoint SHALL accept the following query parameters:
- `limit` (integer, optional, default 20) -- maximum number of notes to return
- `offset` (integer, optional, default 0) -- number of notes to skip for pagination

The results SHALL be ordered by `created_at` descending. Each note MUST include `id`, `contact_id`, `title`, `body`, `emotion`, and `created_at`.

#### Scenario: Fetch notes for a contact

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/notes` is called and the contact has 5 notes
- **THEN** the API MUST return all 5 notes ordered by `created_at` descending
- **AND** each note MUST include `id`, `contact_id`, `title`, `body`, `emotion`, and `created_at`

#### Scenario: Paginate through notes

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/notes?limit=10&offset=10` is called
- **THEN** the API MUST skip the first 10 notes and return at most 10

#### Scenario: Contact has no notes

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/notes` is called and the contact has no notes
- **THEN** the API MUST return an empty list
- **AND** the response status MUST be 200

#### Scenario: Contact does not exist

- **WHEN** `GET /api/butlers/relationship/contacts/nonexistent-uuid/notes` is called
- **THEN** the API MUST return a 404 response with an error message indicating the contact was not found

#### Scenario: Notes display emotion values

- **WHEN** a contact has notes with `emotion` values of `"positive"`, `"neutral"`, and `"negative"`
- **THEN** all three notes MUST be returned with their respective `emotion` values preserved

---

### Requirement: Contact interactions API

The dashboard API SHALL expose `GET /api/butlers/relationship/contacts/:id/interactions` which returns interactions for a specific contact from the `interactions` table via a direct database read.

The endpoint SHALL accept the following query parameters:
- `type` (string, optional) -- filter by interaction type (`'call'`, `'video'`, `'meeting'`, `'message'`, `'email'`)
- `limit` (integer, optional, default 20) -- maximum number of interactions to return
- `offset` (integer, optional, default 0) -- number of interactions to skip for pagination

The results SHALL be ordered by `occurred_at` descending. Each interaction MUST include `id`, `contact_id`, `type`, `direction`, `summary`, `duration_minutes`, `occurred_at`, and `metadata`.

#### Scenario: Fetch all interactions for a contact

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/interactions` is called and the contact has 3 interactions
- **THEN** the API MUST return all 3 interactions ordered by `occurred_at` descending
- **AND** each interaction MUST include `id`, `contact_id`, `type`, `direction`, `summary`, `duration_minutes`, `occurred_at`, and `metadata`

#### Scenario: Filter interactions by type

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/interactions?type=call` is called and the contact has 2 calls and 1 meeting
- **THEN** the API MUST return only the 2 interactions with `type='call'`

#### Scenario: Paginate through interactions

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/interactions?limit=5&offset=5` is called
- **THEN** the API MUST skip the first 5 interactions and return at most 5

#### Scenario: Contact has no interactions

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/interactions` is called and the contact has no interactions
- **THEN** the API MUST return an empty list
- **AND** the response status MUST be 200

#### Scenario: Contact does not exist

- **WHEN** `GET /api/butlers/relationship/contacts/nonexistent-uuid/interactions` is called
- **THEN** the API MUST return a 404 response with an error message indicating the contact was not found

---

### Requirement: Contact gifts API

The dashboard API SHALL expose `GET /api/butlers/relationship/contacts/:id/gifts` which returns gifts for a specific contact from the `gifts` table via a direct database read.

The endpoint SHALL accept the following query parameters:
- `status` (string, optional) -- filter by gift status (`'idea'`, `'searched'`, `'found'`, `'bought'`, `'given'`)
- `limit` (integer, optional, default 20) -- maximum number of gifts to return
- `offset` (integer, optional, default 0) -- number of gifts to skip for pagination

The results SHALL be ordered by `created_at` descending. Each gift MUST include `id`, `contact_id`, `name`, `description`, `status`, `occasion`, `estimated_price_cents`, `url`, `created_at`, and `updated_at`.

#### Scenario: Fetch all gifts for a contact

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/gifts` is called and the contact has 3 gifts
- **THEN** the API MUST return all 3 gifts ordered by `created_at` descending
- **AND** each gift MUST include `id`, `contact_id`, `name`, `description`, `status`, `occasion`, `estimated_price_cents`, `url`, `created_at`, and `updated_at`

#### Scenario: Filter gifts by status

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/gifts?status=idea` is called and the contact has 2 gifts with `status='idea'` and 1 with `status='given'`
- **THEN** the API MUST return only the 2 gifts with `status='idea'`

#### Scenario: Contact has no gifts

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/gifts` is called and the contact has no gifts
- **THEN** the API MUST return an empty list
- **AND** the response status MUST be 200

#### Scenario: Contact does not exist

- **WHEN** `GET /api/butlers/relationship/contacts/nonexistent-uuid/gifts` is called
- **THEN** the API MUST return a 404 response with an error message indicating the contact was not found

---

### Requirement: Contact loans API

The dashboard API SHALL expose `GET /api/butlers/relationship/contacts/:id/loans` which returns loans involving a specific contact from the `loans` table via a direct database read. A loan involves the contact if the contact is either the `lender_contact_id` or the `borrower_contact_id`.

The endpoint SHALL accept the following query parameters:
- `settled` (boolean, optional) -- filter by settled status (`true` for settled loans, `false` for outstanding loans)
- `limit` (integer, optional, default 20) -- maximum number of loans to return
- `offset` (integer, optional, default 0) -- number of loans to skip for pagination

The results SHALL be ordered by `created_at` descending. Each loan MUST include `id`, `lender_contact_id`, `borrower_contact_id`, `name`, `amount_cents`, `currency`, `loaned_at`, `settled`, `settled_at`, `created_at`, and nested objects `lender` and `borrower` each containing the contact's `id`, `first_name`, and `last_name`.

#### Scenario: Fetch all loans for a contact

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/loans` is called and the contact has 2 loans as lender and 1 as borrower
- **THEN** the API MUST return all 3 loans ordered by `created_at` descending
- **AND** each loan MUST include the `lender` and `borrower` nested contact objects

#### Scenario: Filter outstanding loans

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/loans?settled=false` is called and the contact has 1 settled loan and 2 outstanding loans
- **THEN** the API MUST return only the 2 loans with `settled=false`

#### Scenario: Filter settled loans

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/loans?settled=true` is called
- **THEN** the API MUST return only loans with `settled=true`

#### Scenario: Contact has no loans

- **WHEN** `GET /api/butlers/relationship/contacts/abc-123-uuid/loans` is called and the contact has no loans
- **THEN** the API MUST return an empty list
- **AND** the response status MUST be 200

#### Scenario: Contact does not exist

- **WHEN** `GET /api/butlers/relationship/contacts/nonexistent-uuid/loans` is called
- **THEN** the API MUST return a 404 response with an error message indicating the contact was not found

#### Scenario: Loan includes both parties' names

- **WHEN** a loan has `lender_contact_id` pointing to "Alice Smith" and `borrower_contact_id` pointing to "Bob Jones"
- **THEN** the loan object MUST include `lender: {"id": ..., "first_name": "Alice", "last_name": "Smith"}` and `borrower: {"id": ..., "first_name": "Bob", "last_name": "Jones"}`

---

### Requirement: Groups list API

The dashboard API SHALL expose `GET /api/butlers/relationship/groups` which returns all groups from the `groups` table with their member counts via a direct database read.

Each group object in the response MUST include:
- `id` (UUID)
- `name` (string)
- `type` (string or null)
- `member_count` (integer) -- the count of rows in `group_members` for this group
- `created_at` (ISO 8601 timestamp)

The results SHALL be ordered by `name` ascending.

#### Scenario: Fetch all groups with member counts

- **WHEN** `GET /api/butlers/relationship/groups` is called and 3 groups exist with 5, 2, and 0 members respectively
- **THEN** the API MUST return all 3 groups ordered by `name` ascending
- **AND** each group MUST include `id`, `name`, `type`, `member_count`, and `created_at`
- **AND** the member counts MUST be 5, 2, and 0 respectively
- **AND** the response status MUST be 200

#### Scenario: No groups exist

- **WHEN** `GET /api/butlers/relationship/groups` is called and the `groups` table is empty
- **THEN** the API MUST return an empty list
- **AND** the response status MUST be 200

#### Scenario: Group with no members shows zero count

- **WHEN** a group exists with no entries in `group_members`
- **THEN** the group's `member_count` MUST be `0`

---

### Requirement: Group detail API

The dashboard API SHALL expose `GET /api/butlers/relationship/groups/:id` which returns a single group's record with its members via a direct database read.

The response MUST include:
- `id` (UUID)
- `name` (string)
- `type` (string or null)
- `created_at` (ISO 8601 timestamp)
- `members` (array) -- all contacts in the group joined from `group_members` and `contacts`, each containing `contact_id`, `role`, `first_name`, `last_name`, `company`, and `avatar_url`

#### Scenario: Fetch an existing group with members

- **WHEN** `GET /api/butlers/relationship/groups/abc-123-uuid` is called and the group has 3 members
- **THEN** the API MUST return the group record with a `members` array containing all 3 members
- **AND** each member MUST include `contact_id`, `role`, `first_name`, `last_name`, `company`, and `avatar_url`
- **AND** the response status MUST be 200

#### Scenario: Fetch an existing group with no members

- **WHEN** `GET /api/butlers/relationship/groups/abc-123-uuid` is called and the group has no members
- **THEN** the API MUST return the group record with an empty `members` array
- **AND** the response status MUST be 200

#### Scenario: Group does not exist

- **WHEN** `GET /api/butlers/relationship/groups/nonexistent-uuid` is called and no group with that ID exists
- **THEN** the API MUST return a 404 response with an error message indicating the group was not found

---

### Requirement: Labels list API

The dashboard API SHALL expose `GET /api/butlers/relationship/labels` which returns all labels from the `labels` table via a direct database read.

Each label object in the response MUST include:
- `id` (UUID)
- `name` (string)
- `color` (string or null)
- `created_at` (ISO 8601 timestamp)

The results SHALL be ordered by `name` ascending.

#### Scenario: Fetch all labels

- **WHEN** `GET /api/butlers/relationship/labels` is called and 5 labels exist
- **THEN** the API MUST return all 5 labels ordered by `name` ascending
- **AND** each label MUST include `id`, `name`, `color`, and `created_at`
- **AND** the response status MUST be 200

#### Scenario: No labels exist

- **WHEN** `GET /api/butlers/relationship/labels` is called and the `labels` table is empty
- **THEN** the API MUST return an empty list
- **AND** the response status MUST be 200

---

### Requirement: Upcoming dates API

The dashboard API SHALL expose `GET /api/butlers/relationship/upcoming-dates` which returns important dates occurring within the next N days across all contacts, via a direct database read.

The endpoint SHALL accept the following query parameter:
- `days` (integer, optional, default 30) -- the number of days ahead to look for upcoming dates

The comparison SHALL use `month` and `day` matching against the current date, wrapping around the year boundary (e.g., if today is December 29 and `days=7`, January dates within that window MUST be included). The `year` column SHALL be ignored for the purpose of matching -- dates like birthdays recur every year.

Each entry in the response MUST include:
- All columns from `important_dates` (`id`, `label`, `day`, `month`, `year`, `created_at`)
- `contact_id` (UUID)
- `contact_first_name` (string or null)
- `contact_last_name` (string or null)
- `days_away` (integer) -- the number of days until this date occurs (0 = today)

The results SHALL be ordered by `days_away` ascending (soonest first).

#### Scenario: Fetch upcoming dates within default 30-day window

- **WHEN** `GET /api/butlers/relationship/upcoming-dates` is called with no query parameters
- **AND** today is February 10 and a contact has a birthday on February 20 (`month=2`, `day=20`)
- **THEN** the result MUST include that date with `days_away` set to `10`
- **AND** the result MUST include the contact's `first_name` and `last_name`

#### Scenario: Fetch upcoming dates with custom window

- **WHEN** `GET /api/butlers/relationship/upcoming-dates?days=7` is called
- **AND** today is February 10 and a contact has an anniversary on February 14 (`month=2`, `day=14`)
- **THEN** the result MUST include that date with `days_away` set to `4`

#### Scenario: Date outside the window is excluded

- **WHEN** `GET /api/butlers/relationship/upcoming-dates?days=7` is called
- **AND** today is February 10 and a contact has a date on March 15 (`month=3`, `day=15`)
- **THEN** that date MUST NOT be included in the results

#### Scenario: Year-end wrap-around

- **WHEN** `GET /api/butlers/relationship/upcoming-dates?days=7` is called
- **AND** today is December 29 and a contact has a date on January 3 (`month=1`, `day=3`)
- **THEN** that date MUST be included with `days_away` set to `5`

#### Scenario: Dates with null year are included

- **WHEN** a contact has a date with `month=2`, `day=14`, `year=NULL`
- **AND** that date falls within the window
- **THEN** it MUST be included in the results with `year` as `null`

#### Scenario: No upcoming dates

- **WHEN** `GET /api/butlers/relationship/upcoming-dates?days=7` is called and no important dates fall within the next 7 days
- **THEN** the API MUST return an empty list
- **AND** the response status MUST be 200

#### Scenario: Date occurring today has days_away of zero

- **WHEN** today is February 14 and a contact has a date with `month=2`, `day=14`
- **THEN** that date MUST be included with `days_away` set to `0`

#### Scenario: Results ordered by days_away ascending

- **WHEN** multiple dates exist within the window at various distances
- **THEN** the results MUST be ordered by `days_away` ascending so the soonest dates appear first

---

### Requirement: Contacts table page

The frontend SHALL render a contacts page at `/butlers/relationship/contacts` displaying a searchable, filterable, sortable table of contacts from the Relationship butler.

The table SHALL display the following columns:
- **Name** -- `first_name` and `last_name` combined, displayed as a single clickable value that links to the contact detail page
- **Company** -- the `company` value, or a dash if null
- **Labels** -- the contact's assigned labels rendered as colored badges (using each label's `name` and `color`)
- **Last interaction** -- `last_interaction_at` formatted as a human-readable relative timestamp (e.g., "3 days ago", "2 weeks ago"), or "Never" if null

The page SHALL provide the following controls:
- **Search input** -- a text input that filters contacts by name or company. The input SHALL debounce user input (minimum 300ms) before issuing a new API request with the `q` parameter.
- **Label filter** -- a dropdown or multi-select populated from `GET /api/butlers/relationship/labels`, allowing the user to filter contacts by label.
- **Sort controls** -- the Name and Last interaction columns SHALL be sortable. Clicking a column header SHALL toggle ascending/descending sort order.

#### Scenario: Contacts page loads with default view

- **WHEN** a user navigates to `/butlers/relationship/contacts`
- **THEN** the page MUST display the contacts table with the first page of results sorted by name ascending
- **AND** the search input MUST be visible and empty
- **AND** the label filter MUST be visible with no label selected

#### Scenario: User searches by name

- **WHEN** the user types `"smith"` into the search input
- **THEN** after the debounce period, the table MUST update to show only contacts matching `"smith"` in their name, nickname, or company
- **AND** the pagination MUST reset to the first page

#### Scenario: User filters by label

- **WHEN** the user selects the `"VIP"` label from the label filter
- **THEN** the table MUST update to show only contacts that have the `"VIP"` label assigned
- **AND** the URL query parameters SHOULD update to reflect the applied filter

#### Scenario: User sorts by last interaction

- **WHEN** the user clicks the "Last interaction" column header
- **THEN** the table MUST re-sort contacts by `last_interaction_at` descending (most recent first)
- **AND** contacts with null `last_interaction_at` MUST be placed at the end

#### Scenario: User sorts by name descending

- **WHEN** the user clicks the "Name" column header while sorted ascending
- **THEN** the sort order MUST toggle to descending (Z-A)

#### Scenario: User clicks a contact name

- **WHEN** the user clicks on a contact's name in the table
- **THEN** the browser MUST navigate to `/butlers/relationship/contacts/:id` for that contact

#### Scenario: Empty state when no contacts exist

- **WHEN** the Relationship butler has no listed contacts
- **THEN** the page MUST display an empty state message (e.g., "No contacts found")
- **AND** the search input and label filter MUST still be visible

#### Scenario: Pagination controls

- **WHEN** the total number of matching contacts exceeds the page size
- **THEN** pagination controls MUST be visible indicating the current page, total pages, and allowing navigation to previous/next pages

---

### Requirement: Contact detail page

The frontend SHALL render a contact detail page at `/butlers/relationship/contacts/:id` displaying the full contact record with all related data.

The page MUST contain the following sections:

1. **Header card** -- displaying the contact's full name (`first_name` + `last_name`), `company`, `job_title`, `pronouns`, and `avatar_url` (as an image if present, or initials fallback). Assigned labels SHALL be rendered as colored badges. The `nickname` SHALL be displayed in parentheses after the name if present.

2. **Contact info section** -- displaying all `contact_info` entries grouped by `type` (email, phone, social, etc.). Each entry SHALL show the `label` (e.g., "work", "personal") and the `value`. Values of type `email` SHALL be rendered as `mailto:` links. Values of type `phone` SHALL be rendered as `tel:` links.

3. **Important dates section** -- displaying all important dates with a countdown indicator. Each date SHALL show the `label`, the date (`day`/`month`/`year` formatted, with "unknown year" if `year` is null), and the number of days until the next occurrence. Dates occurring within the next 7 days SHALL be visually highlighted (e.g., with a colored badge or accent).

4. **Quick facts section** -- displaying all quick facts, grouped or tagged by `category`. Each fact SHALL show the `category` label and the `content` text.

5. **Relationships section** -- displaying all relationships as a list. Each entry SHALL show the `type` label (e.g., "Parent", "Friend"), the related contact's name as a clickable link to their detail page, and the `group_type`.

6. **Tabbed content area** -- containing four tabs:
   - **Notes** -- paginated list of notes loaded from `/contacts/:id/notes`. Each note SHALL display `title` (if present), `body` text, `emotion` as a colored indicator (green for positive, gray for neutral, red for negative), and `created_at` as a relative timestamp.
   - **Interactions** -- paginated list of interactions loaded from `/contacts/:id/interactions`. Each interaction SHALL display `type` as an icon or badge, `direction` (inbound/outbound), `summary`, `duration_minutes` (if present), and `occurred_at` as a relative timestamp. A type filter dropdown SHALL allow filtering by interaction type.
   - **Gifts** -- paginated list of gifts loaded from `/contacts/:id/gifts`. Each gift SHALL display `name`, `description`, `status` as a colored badge (pipeline stages), `occasion`, `estimated_price_cents` formatted as currency, `url` as a clickable link (if present), and `created_at`.
   - **Loans** -- paginated list of loans loaded from `/contacts/:id/loans`. Each loan SHALL display `name`, `amount_cents` formatted as currency with `currency` code, the other party's name (lender or borrower), `settled` status as a badge, `loaned_at`, and `settled_at` (if settled).

7. **Activity feed sidebar or section** -- displaying the contact's activity feed loaded from `/contacts/:id/feed`, ordered by `created_at` descending. Each entry SHALL display the `action` as a human-readable label, `summary` text, and `created_at` as a relative timestamp. The feed SHALL support "load more" pagination.

#### Scenario: Contact detail page loads with full data

- **WHEN** a user navigates to `/butlers/relationship/contacts/abc-123-uuid` for a contact with info, dates, facts, relationships, notes, interactions, gifts, loans, and feed entries
- **THEN** the header card MUST display the contact's name, company, job title, pronouns, and labels
- **AND** all contact info entries MUST be displayed grouped by type
- **AND** all important dates MUST be displayed with countdown indicators
- **AND** all quick facts MUST be displayed grouped by category
- **AND** all relationships MUST be displayed with related contact names as links
- **AND** the Notes tab MUST be selected by default and display the first page of notes
- **AND** the activity feed MUST display the most recent feed entries

#### Scenario: Contact with no data in some sections

- **WHEN** a user navigates to a contact's detail page and the contact has no notes, interactions, gifts, or loans
- **THEN** each empty tab MUST display an appropriate empty state message (e.g., "No notes yet", "No interactions recorded", "No gift ideas", "No loans")
- **AND** the page MUST render without errors

#### Scenario: User switches between tabs

- **WHEN** the user clicks the "Interactions" tab
- **THEN** the tab content MUST switch to display the interactions list
- **AND** the interactions data MUST be loaded from the API (lazy-loaded on first tab activation)

#### Scenario: Important date with upcoming countdown

- **WHEN** today is February 10 and a contact has a birthday on February 14 (`month=2`, `day=14`)
- **THEN** the important dates section MUST display "4 days away" or similar countdown text
- **AND** the date MUST be visually highlighted as upcoming

#### Scenario: Nickname displayed in header

- **WHEN** a contact has `first_name="Robert"`, `last_name="Smith"`, and `nickname="Bobby"`
- **THEN** the header card MUST display the name as `"Robert (Bobby) Smith"` or equivalent formatting that includes the nickname

#### Scenario: Email and phone values are clickable

- **WHEN** a contact has a `contact_info` entry with `type='email'` and `value='alice@example.com'`
- **THEN** the value MUST be rendered as a clickable `mailto:alice@example.com` link
- **WHEN** a contact has a `contact_info` entry with `type='phone'` and `value='+1-555-0100'`
- **THEN** the value MUST be rendered as a clickable `tel:+1-555-0100` link

#### Scenario: Relationship links navigate to related contact

- **WHEN** a contact has a relationship with another contact
- **THEN** the related contact's name MUST be a clickable link
- **AND** clicking it MUST navigate to `/butlers/relationship/contacts/:related_contact_id`

#### Scenario: Gift status displayed as pipeline

- **WHEN** the Gifts tab displays a gift with `status='bought'`
- **THEN** the status MUST be rendered as a colored badge indicating the gift's position in the pipeline (idea -> searched -> found -> bought -> given)

#### Scenario: Loan direction is clear

- **WHEN** the Loans tab displays a loan where the current contact is the `lender_contact_id`
- **THEN** the display MUST clearly indicate that the current contact lent money to the borrower (e.g., "Lent to Bob Jones")
- **WHEN** the current contact is the `borrower_contact_id`
- **THEN** the display MUST clearly indicate that the current contact borrowed from the lender (e.g., "Borrowed from Alice Smith")

#### Scenario: Activity feed load more

- **WHEN** the activity feed has more entries than the initial page size (50)
- **THEN** a "Load more" button or infinite scroll MUST be available to fetch the next page of feed entries

#### Scenario: Contact not found

- **WHEN** a user navigates to `/butlers/relationship/contacts/nonexistent-uuid` and the contact does not exist
- **THEN** the page MUST display a 404 message (e.g., "Contact not found")

---

### Requirement: Groups page

The frontend SHALL render a groups page at `/butlers/relationship/groups` displaying a list of all groups from the Relationship butler.

Each group in the list SHALL display:
- **Name** -- the group's `name` as a clickable value that links to the group detail page
- **Type** -- the group's `type` (e.g., "family", "couple", "friends", "team"), or a dash if null
- **Members** -- the `member_count` displayed as a badge (e.g., "5 members")

Clicking a group name SHALL navigate to `/butlers/relationship/groups/:id`.

The group detail page SHALL display:
- **Group header** -- the group's `name` and `type`
- **Member list** -- a list of all members, each showing the contact's name (as a clickable link to their contact detail page), `role` in the group (if present), `company`, and `avatar_url` (as an image or initials fallback)

#### Scenario: Groups page loads with groups

- **WHEN** a user navigates to `/butlers/relationship/groups` and 3 groups exist
- **THEN** the page MUST display all 3 groups with their names, types, and member counts

#### Scenario: Groups page with no groups

- **WHEN** a user navigates to `/butlers/relationship/groups` and no groups exist
- **THEN** the page MUST display an empty state message (e.g., "No groups created yet")

#### Scenario: User clicks a group name

- **WHEN** the user clicks on a group's name
- **THEN** the browser MUST navigate to `/butlers/relationship/groups/:id`

#### Scenario: Group detail page loads with members

- **WHEN** a user navigates to `/butlers/relationship/groups/abc-123-uuid` and the group has 4 members
- **THEN** the page MUST display the group header with name and type
- **AND** the member list MUST display all 4 members with their names, roles, companies, and avatars

#### Scenario: Group detail page with no members

- **WHEN** a user navigates to a group's detail page and the group has no members
- **THEN** the member list MUST display an empty state message (e.g., "No members in this group")

#### Scenario: Member name links to contact detail

- **WHEN** a member is displayed in the group detail page
- **THEN** the member's name MUST be a clickable link
- **AND** clicking it MUST navigate to `/butlers/relationship/contacts/:contact_id`

#### Scenario: Group not found

- **WHEN** a user navigates to `/butlers/relationship/groups/nonexistent-uuid` and no group with that ID exists
- **THEN** the page MUST display a 404 message (e.g., "Group not found")
