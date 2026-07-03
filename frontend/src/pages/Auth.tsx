import { useEffect, useRef, useState, type ChangeEvent, type FormEvent, type KeyboardEvent } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import Button from '../components/Button'
import Input from '../components/Input'
import Select from '../components/Select'
import Tag from '../components/Tag'
import logoDark from '../utils/dark/logo.png'
import logoLight from '../utils/white/logo.png'
import { useTheme } from '../utils/useTheme'
import {
  createSkill,
  fetchSignupMetadata,
  signupCandidate,
  signinCandidate,
  signupRecruiter,
  signinRecruiter,
  type JobRole,
  type Skill,
} from '../api/auth'
import '../css/Auth.css'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/
const NAME_RE = /^[a-zA-Z\s'\-]+$/
const CV_MAX_BYTES = 5 * 1024 * 1024

function blockNonNumericKey(e: KeyboardEvent<HTMLInputElement>) {
  if (['e', 'E', '+', '-'].includes(e.key)) e.preventDefault()
}

type AccountType = 'candidate' | 'recruiter'
type AuthMode = 'signin' | 'signup'

function Auth() {
  const navigate = useNavigate()
  const location = useLocation()
  const theme = useTheme()
  const logo = theme === 'light' ? logoLight : logoDark
  const pendingJobId = (location.state as { pendingJobId?: string } | null)?.pendingJobId
  const [accountType, setAccountType] = useState<AccountType>('candidate')
  const [mode, setMode] = useState<AuthMode>('signin')

  // Sign-in form state (shared)
  const [signinEmail, setSigninEmail] = useState('')
  const [signinPassword, setSigninPassword] = useState('')

  // Shared signup fields
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [signupEmail, setSignupEmail] = useState('')
  const [signupPassword, setSignupPassword] = useState('')

  // Candidate-only signup state
  const [jobRoles, setJobRoles] = useState<JobRole[]>([])
  const [allSkills, setAllSkills] = useState<Skill[]>([])
  const [metaLoading, setMetaLoading] = useState(false)
  const [metaError, setMetaError] = useState<string | null>(null)
  const [selectedRoleId, setSelectedRoleId] = useState<number | ''>('')
  const [selectedSkills, setSelectedSkills] = useState<Skill[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [customSkillName, setCustomSkillName] = useState('')
  const [addingCustomSkill, setAddingCustomSkill] = useState(false)
  const [customSkillError, setCustomSkillError] = useState<string | null>(null)
  const [experience, setExperience] = useState('')
  const [cvFile, setCvFile] = useState<File | null>(null)
  const cvInputRef = useRef<HTMLInputElement>(null)

  // Recruiter-only signup state
  const [companyName, setCompanyName] = useState('')
  const [designation, setDesignation] = useState('')

  // Password visibility
  const [showSigninPassword, setShowSigninPassword] = useState(false)
  const [showSignupPassword, setShowSignupPassword] = useState(false)

  // Submission state
  const [submitting, setSubmitting] = useState(false)
  const [attemptedSubmit, setAttemptedSubmit] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitSuccess, setSubmitSuccess] = useState(false)

  const suggestedSkills =
    selectedRoleId !== ''
      ? allSkills.filter(
          (s) =>
            s.job_role_ids.includes(selectedRoleId as number) &&
            !selectedSkills.some((sel) => sel.id === s.id),
        )
      : []

  useEffect(() => {
    if (mode !== 'signup' || accountType !== 'candidate') return
    setMetaLoading(true)
    setMetaError(null)
    fetchSignupMetadata()
      .then(({ job_roles, skills }) => {
        setJobRoles(job_roles)
        setAllSkills(skills)
      })
      .catch((err: unknown) => setMetaError(err instanceof Error ? err.message : 'Failed to load options'))
      .finally(() => setMetaLoading(false))
  }, [mode, accountType])

  function handleAccountTypeChange(type: AccountType) {
    setAccountType(type)
    setSubmitError(null)
    setSubmitSuccess(false)
    setAttemptedSubmit(false)
  }

  function handleRoleChange(event: ChangeEvent<HTMLSelectElement>) {
    setSelectedRoleId(Number(event.target.value))
    setSelectedSkills([])
    setShowSuggestions(false)
  }

  function handleAddSkill(skill: Skill) {
    setSelectedSkills((prev) => [...prev, skill])
  }

  function handleRemoveSkill(skillId: number) {
    setSelectedSkills((prev) => prev.filter((s) => s.id !== skillId))
  }

  function handleAddAllSkills() {
    if (suggestedSkills.length === 0) return
    setSelectedSkills((prev) => [...prev, ...suggestedSkills])
  }

  async function handleAddCustomSkill() {
    const name = customSkillName.trim()
    if (!name) return
    setAddingCustomSkill(true)
    setCustomSkillError(null)
    try {
      const skill = await createSkill(name, selectedRoleId === '' ? null : selectedRoleId)
      setAllSkills((prev) => (prev.some((s) => s.id === skill.id) ? prev : [...prev, skill]))
      setSelectedSkills((prev) => (prev.some((s) => s.id === skill.id) ? prev : [...prev, skill]))
      setCustomSkillName('')
    } catch (err) {
      setCustomSkillError(err instanceof Error ? err.message : 'Failed to add skill')
    } finally {
      setAddingCustomSkill(false)
    }
  }

  function handleCvChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null
    if (file && file.size > CV_MAX_BYTES) {
      setSubmitError('CV file must be under 5 MB.')
      setCvFile(null)
      event.target.value = ''
    } else {
      setSubmitError(null)
      setCvFile(file)
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAttemptedSubmit(true)

    if (mode === 'signin') {
      if (!signinEmail || !EMAIL_RE.test(signinEmail) || !signinPassword) return
      setSubmitting(true)
      setSubmitError(null)
      try {
        if (accountType === 'candidate') {
          const result = await signinCandidate(signinEmail, signinPassword)
          sessionStorage.setItem('candidateId', result.candidate_id)
          sessionStorage.setItem('candidateEmail', signinEmail)
          sessionStorage.setItem('userType', 'candidate')
          navigate('/my-applications', { state: { candidateId: result.candidate_id } })
        } else {
          const result = await signinRecruiter(signinEmail, signinPassword)
          sessionStorage.setItem('recruiterId', result.recruiter_id)
          sessionStorage.setItem('recruiterEmail', signinEmail)
          sessionStorage.setItem('userType', 'recruiter')
          navigate('/recruiter-dashboard', { state: { recruiterId: result.recruiter_id } })
        }
      } catch (err: unknown) {
        setSubmitError(err instanceof Error ? err.message : 'Sign in failed')
      } finally {
        setSubmitting(false)
      }
      return
    }

    // Signup validation
    const nameOk = (v: string) => !!v && NAME_RE.test(v)
    const emailOk = (v: string) => !!v && EMAIL_RE.test(v)
    const expVal = parseFloat(experience)
    const expOk = !!experience && !isNaN(expVal) && expVal >= 0 && expVal <= 60
    if (accountType === 'recruiter') {
      if (!nameOk(firstName) || !nameOk(lastName) || !emailOk(signupEmail) || !signupPassword || signupPassword.length < 8 || !companyName || !designation) return
    } else {
      if (!nameOk(firstName) || !nameOk(lastName) || !emailOk(signupEmail) || !signupPassword || signupPassword.length < 8 || selectedRoleId === '' || selectedSkills.length === 0 || !expOk || !cvFile) return
    }

    setSubmitting(true)
    setSubmitError(null)
    try {
      if (accountType === 'candidate') {
        if (selectedRoleId === '') return
        await signupCandidate({
          firstName,
          lastName,
          email: signupEmail,
          password: signupPassword,
          jobRoleId: selectedRoleId as number,
          skillIds: selectedSkills.map((s) => s.id),
          experienceYears: parseFloat(experience),
          cv: cvFile,
        })
      } else {
        await signupRecruiter({
          firstName,
          lastName,
          email: signupEmail,
          password: signupPassword,
          companyName,
          designation,
        })
      }
      setSubmitSuccess(true)
    } catch (err: unknown) {
      if (accountType === 'candidate' && cvFile && err instanceof TypeError) {
        // Browser-level upload abort (e.g. Chrome's net::ERR_UPLOAD_FILE_CHANGED) —
        // the selected file was modified/replaced on disk after being chosen, so its
        // File handle is no longer valid. Force a re-select rather than letting the
        // user retry with the same stale handle.
        setCvFile(null)
        if (cvInputRef.current) cvInputRef.current.value = ''
        setSubmitError('Your CV file could not be uploaded — it may have changed on disk after you selected it. Please choose the file again.')
      } else {
        setSubmitError(err instanceof Error ? err.message : 'Signup failed')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (submitSuccess) {
    return (
      <main className="auth-page">
        <div className="auth-card">
          <Link to="/" className="auth-brand">
            <span className="auth-brand-title">
              <span className="auth-brand-primary">Russel</span>
              <span className="auth-brand-accent">.AI</span>
            </span>
            <img src={logo} alt="Russel.AI logo" className="auth-logo" />
          </Link>
          <p className="auth-success-message">Account created! You can now sign in.</p>
          <Button
            type="button"
            variant="primary"
            className="auth-submit"
            onClick={() => {
              setSubmitSuccess(false)
              setMode('signin')
            }}
          >
            Go to Sign In
          </Button>
        </div>
      </main>
    )
  }

  return (
    <main className="auth-page">
      <button type="button" className="auth-back-btn" onClick={() => navigate('/')} aria-label="Back to home">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Back
      </button>

      <div className="auth-card">
        <Link to="/" className="auth-brand">
          <span className="auth-brand-title">
            <span className="auth-brand-primary">Russel</span>
            <span className="auth-brand-accent">.AI</span>
          </span>
          <img src={logo} alt="Russel.AI logo" className="auth-logo" />
        </Link>

        <div className="auth-toggle-group" role="tablist" aria-label="Account type">
          <button
            type="button"
            role="tab"
            aria-selected={accountType === 'candidate'}
            className={`auth-toggle ${accountType === 'candidate' ? 'auth-toggle-active' : ''}`}
            onClick={() => handleAccountTypeChange('candidate')}
          >
            Candidate
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={accountType === 'recruiter'}
            className={`auth-toggle ${accountType === 'recruiter' ? 'auth-toggle-active' : ''}`}
            onClick={() => handleAccountTypeChange('recruiter')}
          >
            Recruiter
          </button>
        </div>

        <div className="auth-toggle-group" role="tablist" aria-label="Sign in or sign up">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'signin'}
            className={`auth-toggle ${mode === 'signin' ? 'auth-toggle-active' : ''}`}
            onClick={() => { setMode('signin'); setAttemptedSubmit(false) }}
          >
            Sign In
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'signup'}
            className={`auth-toggle ${mode === 'signup' ? 'auth-toggle-active' : ''}`}
            onClick={() => { setMode('signup'); setAttemptedSubmit(false) }}
          >
            Sign Up
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          {mode === 'signin' ? (
            <>
              <label className="field">
                <span className="field-label">
                  Email<span className="required-star"> *</span>
                </span>
                <Input
                  type="email"
                  name="email"
                  placeholder="Enter your email"
                  value={signinEmail}
                  onChange={(e) => setSigninEmail(e.target.value)}
                />
                {attemptedSubmit && (!signinEmail
                  ? <span className="field-error">Email is required.</span>
                  : !EMAIL_RE.test(signinEmail)
                    ? <span className="field-error">Enter a valid email address.</span>
                    : null)}
              </label>
              <label className="field">
                <span className="field-label">
                  Password<span className="required-star"> *</span>
                </span>
                <div className="password-wrapper">
                  <Input
                    type={showSigninPassword ? 'text' : 'password'}
                    name="password"
                    placeholder="Enter your password"
                    value={signinPassword}
                    onChange={(e) => setSigninPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowSigninPassword((v) => !v)}
                    aria-label={showSigninPassword ? 'Hide password' : 'Show password'}
                  >
                    {showSigninPassword ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                        <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                        <line x1="1" y1="1" x2="23" y2="23"/>
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                    )}
                  </button>
                </div>
                {attemptedSubmit && !signinPassword && (
                  <span className="field-error">Password is required.</span>
                )}
              </label>
              {submitError && <p className="auth-submit-error">{submitError}</p>}
            </>
          ) : accountType === 'recruiter' ? (
            <>
              <div className="auth-name-row">
                <label className="field">
                  <span className="field-label">
                    First Name<span className="required-star"> *</span>
                  </span>
                  <Input
                    type="text"
                    name="first_name"
                    placeholder="First name"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                  />
                  {attemptedSubmit && (!firstName
                    ? <span className="field-error">First name is required.</span>
                    : !NAME_RE.test(firstName)
                      ? <span className="field-error">Name may only contain letters, spaces, hyphens, and apostrophes.</span>
                      : null)}
                </label>
                <label className="field">
                  <span className="field-label">
                    Last Name<span className="required-star"> *</span>
                  </span>
                  <Input
                    type="text"
                    name="last_name"
                    placeholder="Last name"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                  />
                  {attemptedSubmit && (!lastName
                    ? <span className="field-error">Last name is required.</span>
                    : !NAME_RE.test(lastName)
                      ? <span className="field-error">Name may only contain letters, spaces, hyphens, and apostrophes.</span>
                      : null)}
                </label>
              </div>

              <label className="field">
                <span className="field-label">
                  Email<span className="required-star"> *</span>
                </span>
                <Input
                  type="email"
                  name="email"
                  placeholder="Enter your email"
                  value={signupEmail}
                  onChange={(e) => setSignupEmail(e.target.value)}
                />
                {attemptedSubmit && (!signupEmail
                  ? <span className="field-error">Email is required.</span>
                  : !EMAIL_RE.test(signupEmail)
                    ? <span className="field-error">Enter a valid email address.</span>
                    : null)}
              </label>

              <label className="field">
                <span className="field-label">
                  Password<span className="required-star"> *</span>
                </span>
                <div className="password-wrapper">
                  <Input
                    type={showSignupPassword ? 'text' : 'password'}
                    name="password"
                    placeholder="min 8 characters"
                    value={signupPassword}
                    onChange={(e) => setSignupPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowSignupPassword((v) => !v)}
                    aria-label={showSignupPassword ? 'Hide password' : 'Show password'}
                  >
                    {showSignupPassword ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                        <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                        <line x1="1" y1="1" x2="23" y2="23"/>
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                    )}
                  </button>
                </div>
                {attemptedSubmit && (!signupPassword
                  ? <span className="field-error">Password is required.</span>
                  : signupPassword.length < 8
                    ? <span className="field-error">Password must be at least 8 characters.</span>
                    : null)}
              </label>

              <label className="field">
                <span className="field-label">
                  Company Name<span className="required-star"> *</span>
                </span>
                <Input
                  type="text"
                  name="company_name"
                  placeholder="e.g. Acme Corp"
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                />
                {attemptedSubmit && !companyName && (
                  <span className="field-error">Company name is required.</span>
                )}
              </label>

              <label className="field">
                <span className="field-label">
                  Your Job Title<span className="required-star"> *</span>
                </span>
                <Input
                  type="text"
                  name="designation"
                  placeholder="e.g. Head of Talent"
                  value={designation}
                  onChange={(e) => setDesignation(e.target.value)}
                />
                {attemptedSubmit && !designation && (
                  <span className="field-error">Job title is required.</span>
                )}
              </label>

              {submitError && <p className="auth-submit-error">{submitError}</p>}
            </>
          ) : metaLoading ? (
            <p className="auth-meta-loading">Loading options…</p>
          ) : metaError ? (
            <p className="auth-meta-error">{metaError}</p>
          ) : (
            <>
              <div className="auth-name-row">
                <label className="field">
                  <span className="field-label">
                    First Name<span className="required-star"> *</span>
                  </span>
                  <Input
                    type="text"
                    name="first_name"
                    placeholder="First name"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                  />
                  {attemptedSubmit && (!firstName
                    ? <span className="field-error">First name is required.</span>
                    : !NAME_RE.test(firstName)
                      ? <span className="field-error">Name may only contain letters, spaces, hyphens, and apostrophes.</span>
                      : null)}
                </label>
                <label className="field">
                  <span className="field-label">
                    Last Name<span className="required-star"> *</span>
                  </span>
                  <Input
                    type="text"
                    name="last_name"
                    placeholder="Last name"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                  />
                  {attemptedSubmit && (!lastName
                    ? <span className="field-error">Last name is required.</span>
                    : !NAME_RE.test(lastName)
                      ? <span className="field-error">Name may only contain letters, spaces, hyphens, and apostrophes.</span>
                      : null)}
                </label>
              </div>

              <label className="field">
                <span className="field-label">
                  Email<span className="required-star"> *</span>
                </span>
                <Input
                  type="email"
                  name="email"
                  placeholder="Enter your email"
                  value={signupEmail}
                  onChange={(e) => setSignupEmail(e.target.value)}
                />
                {attemptedSubmit && (!signupEmail
                  ? <span className="field-error">Email is required.</span>
                  : !EMAIL_RE.test(signupEmail)
                    ? <span className="field-error">Enter a valid email address.</span>
                    : null)}
              </label>

              <label className="field">
                <span className="field-label">
                  Password<span className="required-star"> *</span>
                </span>
                <div className="password-wrapper">
                  <Input
                    type={showSignupPassword ? 'text' : 'password'}
                    name="password"
                    placeholder="min 8 characters"
                    value={signupPassword}
                    onChange={(e) => setSignupPassword(e.target.value)}
                  />
                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowSignupPassword((v) => !v)}
                    aria-label={showSignupPassword ? 'Hide password' : 'Show password'}
                  >
                    {showSignupPassword ? (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/>
                        <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/>
                        <line x1="1" y1="1" x2="23" y2="23"/>
                      </svg>
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                        <circle cx="12" cy="12" r="3"/>
                      </svg>
                    )}
                  </button>
                </div>
                {attemptedSubmit && (!signupPassword
                  ? <span className="field-error">Password is required.</span>
                  : signupPassword.length < 8
                    ? <span className="field-error">Password must be at least 8 characters.</span>
                    : null)}
              </label>

              <div className="field">
                <span className="field-label">
                  Job Title / Role & Skills<span className="required-star"> *</span>
                </span>
                <div className="skillset-row">
                  <Select value={selectedRoleId} onChange={handleRoleChange}>
                    <option value="" disabled>
                      Select a role
                    </option>
                    {jobRoles.map((role) => (
                      <option key={role.id} value={role.id}>
                        {role.title}
                      </option>
                    ))}
                  </Select>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={selectedRoleId === ''}
                    onClick={() => setShowSuggestions(true)}
                  >
                    Add Skills
                  </Button>
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={selectedRoleId === '' || suggestedSkills.length === 0}
                    onClick={handleAddAllSkills}
                  >
                    Add All
                  </Button>
                </div>

                {attemptedSubmit && selectedRoleId === '' && (
                  <span className="field-error">Please select a job role.</span>
                )}
                {attemptedSubmit && selectedRoleId !== '' && selectedSkills.length === 0 && (
                  <span className="field-error">Please add at least one skill.</span>
                )}

                {showSuggestions && suggestedSkills.length > 0 && (
                  <div className="skill-suggestions">
                    <span className="skill-suggestions-label">Tap to add</span>
                    <div className="tag-list">
                      {suggestedSkills.map((skill) => (
                        <Tag key={skill.id} onClick={() => handleAddSkill(skill)}>
                          {skill.name}
                        </Tag>
                      ))}
                    </div>
                  </div>
                )}

                <div className="skillset-row skillset-custom-row">
                  <Input
                    type="text"
                    placeholder="Add a custom skill…"
                    value={customSkillName}
                    onChange={(e) => setCustomSkillName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        void handleAddCustomSkill()
                      }
                    }}
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={!customSkillName.trim() || addingCustomSkill}
                    onClick={() => void handleAddCustomSkill()}
                  >
                    {addingCustomSkill ? 'Adding…' : 'Add Custom'}
                  </Button>
                </div>
                {customSkillError && <span className="field-error">{customSkillError}</span>}

                {selectedSkills.length > 0 && (
                  <div className="tag-list selected-skills">
                    {selectedSkills.map((skill) => (
                      <Tag key={skill.id} variant="active" onRemove={() => handleRemoveSkill(skill.id)}>
                        {skill.name}
                      </Tag>
                    ))}
                  </div>
                )}
              </div>

              <label className="field">
                <span className="field-label">
                  Total Experience (years)<span className="required-star"> *</span>
                </span>
                <Input
                  type="number"
                  name="experience"
                  min="0"
                  max="60"
                  step="0.5"
                  placeholder="e.g. 2.5"
                  value={experience}
                  onChange={(e) => setExperience(e.target.value)}
                  onKeyDown={blockNonNumericKey}
                />
                {attemptedSubmit && (!experience
                  ? <span className="field-error">Experience is required.</span>
                  : (isNaN(parseFloat(experience)) || parseFloat(experience) < 0 || parseFloat(experience) > 60)
                    ? <span className="field-error">Enter a value between 0 and 60.</span>
                    : null)}
              </label>

              <div className="field">
                <span className="field-label">
                  CV / Resume<span className="required-star"> *</span>
                </span>
                <label className="file-input">
                  <input ref={cvInputRef} type="file" accept=".pdf,.doc,.docx" onChange={handleCvChange} hidden />
                  <span className="file-input-button">Choose File</span>
                  <span className="file-input-name">{cvFile ? cvFile.name : 'No file selected'}</span>
                </label>
                {attemptedSubmit && !cvFile && !submitError && (
                  <span className="field-error">CV / Resume is required.</span>
                )}
              </div>

              {submitError && <p className="auth-submit-error">{submitError}</p>}
            </>
          )}

          <Button type="submit" variant="primary" className="auth-submit" disabled={submitting}>
            {mode === 'signin'
              ? submitting ? 'Signing In…' : 'Sign In'
              : submitting ? 'Creating Account…' : 'Create Account'}
          </Button>
        </form>
      </div>
    </main>
  )
}

export default Auth
