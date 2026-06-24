import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Tag from '../components/Tag'
import { fetchCandidateProfile, fetchRecruiterProfile, type CandidateProfile, type RecruiterProfile } from '../api/profile'
import '../css/UserProfile.css'

type UserType = 'candidate' | 'recruiter'

function UserProfile() {
  const navigate = useNavigate()
  const userType = sessionStorage.getItem('userType') as UserType | null
  const candidateId = sessionStorage.getItem('candidateId')
  const recruiterId = sessionStorage.getItem('recruiterId')

  const [candidateProfile, setCandidateProfile] = useState<CandidateProfile | null>(null)
  const [recruiterProfile, setRecruiterProfile] = useState<RecruiterProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!userType || (!candidateId && !recruiterId)) {
      navigate('/auth')
      return
    }

    setLoading(true)
    setError(null)

    const fetch =
      userType === 'candidate' && candidateId
        ? fetchCandidateProfile(candidateId).then((p) => setCandidateProfile(p))
        : recruiterId
          ? fetchRecruiterProfile(recruiterId).then((p) => setRecruiterProfile(p))
          : Promise.reject(new Error('No session found'))

    fetch
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'Failed to load profile'))
      .finally(() => setLoading(false))
  }, [userType, candidateId, recruiterId, navigate])

  const profile = userType === 'candidate' ? candidateProfile : recruiterProfile
  const displayName = profile ? `${profile.first_name} ${profile.last_name}` : ''
  const initials = profile
    ? `${profile.first_name[0] ?? ''}${profile.last_name[0] ?? ''}`.toUpperCase()
    : '?'

  return (
    <main className="profile-page">
      <div className="profile-scroll-area">
        {loading ? (
          <div className="profile-loading">
            <div className="profile-spinner" />
          </div>
        ) : error ? (
          <div className="profile-error">{error}</div>
        ) : userType === 'candidate' && candidateProfile ? (
          <CandidateView profile={candidateProfile} initials={initials} displayName={displayName} />
        ) : userType === 'recruiter' && recruiterProfile ? (
          <RecruiterView profile={recruiterProfile} initials={initials} displayName={displayName} />
        ) : null}
      </div>
    </main>
  )
}

function CandidateView({
  profile,
  initials,
  displayName,
}: {
  profile: CandidateProfile
  initials: string
  displayName: string
}) {
  return (
    <div className="profile-content">
      <div className="profile-header">
        <div className="profile-avatar">{initials}</div>
        <div className="profile-header-info">
          <h1 className="profile-name">{displayName}</h1>
          <div className="profile-meta-row">
            <span className="profile-type-badge">Candidate</span>
            {profile.open_to_work && <span className="profile-open-badge">Open to Work</span>}
          </div>
          <span className="profile-since">Member since {profile.member_since}</span>
        </div>
      </div>

      <section className="profile-card">
        <h2 className="profile-section-title">Role & Experience</h2>
        <div className="profile-field-grid">
          <div className="profile-field">
            <span className="profile-field-label">Job Title</span>
            <span className="profile-field-value">{profile.job_role_title}</span>
          </div>
          <div className="profile-field">
            <span className="profile-field-label">Experience Level</span>
            <span className="profile-field-value">{profile.experience_level}</span>
          </div>
          {profile.current_location && (
            <div className="profile-field">
              <span className="profile-field-label">Location</span>
              <span className="profile-field-value">{profile.current_location}</span>
            </div>
          )}
          <div className="profile-field">
            <span className="profile-field-label">Email</span>
            <span className="profile-field-value">{profile.email}</span>
          </div>
        </div>
      </section>

      <section className="profile-card">
        <h2 className="profile-section-title">Skills</h2>
        {profile.skills.length > 0 ? (
          <div className="profile-skills">
            {profile.skills.map((skill) => (
              <Tag key={skill} variant="active">
                {skill}
              </Tag>
            ))}
          </div>
        ) : (
          <p className="profile-empty">No skills added yet.</p>
        )}
      </section>

      {(profile.bio || profile.linkedin_url) && (
        <section className="profile-card">
          <h2 className="profile-section-title">About</h2>
          <div className="profile-field-grid">
            {profile.bio && (
              <div className="profile-field profile-field--full">
                <span className="profile-field-label">Bio</span>
                <p className="profile-field-value profile-bio">{profile.bio}</p>
              </div>
            )}
            {profile.linkedin_url && (
              <div className="profile-field">
                <span className="profile-field-label">LinkedIn</span>
                <a
                  href={profile.linkedin_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="profile-link"
                >
                  {profile.linkedin_url}
                </a>
              </div>
            )}
          </div>
        </section>
      )}

      <section className="profile-card">
        <h2 className="profile-section-title">CV / Resume</h2>
        {profile.resume_url ? (
          <div className="profile-cv-row">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="profile-cv-icon">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            <span className="profile-cv-name">CV uploaded</span>
          </div>
        ) : (
          <p className="profile-empty">No CV uploaded.</p>
        )}
      </section>
    </div>
  )
}

function RecruiterView({
  profile,
  initials,
  displayName,
}: {
  profile: RecruiterProfile
  initials: string
  displayName: string
}) {
  return (
    <div className="profile-content">
      <div className="profile-header">
        <div className="profile-avatar">{initials}</div>
        <div className="profile-header-info">
          <h1 className="profile-name">{displayName}</h1>
          <div className="profile-meta-row">
            <span className="profile-type-badge profile-type-badge--recruiter">Recruiter</span>
            {profile.company_verified && (
              <span className="profile-verified-badge">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                Verified
              </span>
            )}
          </div>
          <span className="profile-since">Member since {profile.member_since}</span>
        </div>
      </div>

      <section className="profile-card">
        <h2 className="profile-section-title">Company & Role</h2>
        <div className="profile-field-grid">
          <div className="profile-field">
            <span className="profile-field-label">Company</span>
            <span className="profile-field-value">{profile.company_name}</span>
          </div>
          <div className="profile-field">
            <span className="profile-field-label">Job Title</span>
            <span className="profile-field-value">{profile.designation}</span>
          </div>
          <div className="profile-field">
            <span className="profile-field-label">Company Status</span>
            <span className={`profile-field-value ${profile.company_verified ? 'profile-verified-text' : 'profile-pending-text'}`}>
              {profile.company_verified ? 'Verified' : 'Pending verification'}
            </span>
          </div>
        </div>
      </section>

      <section className="profile-card">
        <h2 className="profile-section-title">Account</h2>
        <div className="profile-field-grid">
          <div className="profile-field">
            <span className="profile-field-label">Email</span>
            <span className="profile-field-value">{profile.email}</span>
          </div>
          <div className="profile-field">
            <span className="profile-field-label">Member Since</span>
            <span className="profile-field-value">{profile.member_since}</span>
          </div>
        </div>
      </section>
    </div>
  )
}

export default UserProfile
