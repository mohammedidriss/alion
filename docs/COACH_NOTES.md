# Coach Notes System

## Overview

Coaches can write free-form observation notes about any fighter assigned to
them. These notes appear in the fighter's **Observations** tab alongside
AI-generated analysis and session-level notes, giving a complete picture of
coaching feedback over time.

## Data Model

### `CoachNote` table

| Column      | Type     | Description                        |
|-------------|----------|------------------------------------|
| id          | int (PK) | Auto-increment primary key         |
| coach_id    | UUID FK  | References `coach.id`              |
| fighter_id  | UUID FK  | References `fighter.id`            |
| content     | text     | Free-form note body (min 1 char)   |
| created_at  | datetime | UTC timestamp, set on creation     |

Indexes on `coach_id` and `fighter_id` for fast lookups from both sides.

### Read DTO (`CoachNoteRead`)

Denormalises coach name and photo so the UI doesn't need N+1 queries.

## API Endpoints

### Coach-side

| Method | Path                                          | Description                          |
|--------|-----------------------------------------------|--------------------------------------|
| GET    | `/coaches/{id}/fighters`                      | List fighters currently assigned     |
| POST   | `/coaches/{id}/fighters/{fid}/notes`          | Create a note (body: `{content}`)    |
| GET    | `/coaches/{id}/notes`                         | All notes by this coach, newest first|
| DELETE | `/coaches/{id}/notes/{note_id}`               | Delete a note (coach must own it)    |

### Fighter-side

| Method | Path                              | Description                             |
|--------|-----------------------------------|-----------------------------------------|
| GET    | `/fighters/{id}/coach-notes`      | All notes on this fighter, newest first |

## Frontend

### Coach profile page (`/coaches/[id]`)

- **Assigned Fighters** section lists active assignments with a "+ Note" button
  on each fighter row.
- Clicking "+ Note" opens an inline textarea form to write and save notes.
- **Recent Notes** section shows all notes by this coach with delete option.

### Fighter observations page (`/fighters/[id]/observations`)

- **Coach Notes** section shows notes from all assigned coaches with avatar,
  name, date, and content.
- Session-level notes (legacy) appear below with a separator.
- The headline strip counts both coach notes and session notes.

## Flow

1. Admin assigns a coach to a fighter on the fighter's Team tab (existing).
2. Coach opens their profile → sees assigned fighters.
3. Coach clicks "+ Note" on a fighter → writes observation → saves.
4. Note appears in coach's "Recent Notes" and fighter's "Observations" tab.
