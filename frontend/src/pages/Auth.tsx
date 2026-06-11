import { useState, type ChangeEvent, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import Button from '../components/Button'
import Input from '../components/Input'
import Select from '../components/Select'
import Tag from '../components/Tag'
import BackButton from '../components/BackButton'
import logo from '../utils/logo.png'
import { JOB_ROLES, ROLE_SKILLS } from '../data/roles'
import '../css/Auth.css'

type AccountType = 'candidate' | 'recruiter'
type AuthMode = 'signin' | 'signup'

function Auth() {
  const [accountType, setAccountType] = useState<AccountType>('candidate')
  const [mode, setMode] = useState<AuthMode>('signin')

  const [jobRole, setJobRole] = useState('')
  const [skillRole, setSkillRole] = useState<(typeof JOB_ROLES)[number] | ''>('')
  const [skills, setSkills] = useState<string[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [experience, setExperience] = useState('')
  const [cvFile, setCvFile] = useState<File | null>(null)

  const suggestedSkills = skillRole ? ROLE_SKILLS[skillRole].filter((skill) => !skills.includes(skill)) : []

  function handleJobRoleChange(event: ChangeEvent<HTMLSelectElement>) {
    const value = event.target.value
    setJobRole(value)
    setSkillRole((prev) => prev || (value as (typeof JOB_ROLES)[number]))
  }

  function handleSkillRoleChange(event: ChangeEvent<HTMLSelectElement>) {
    setSkillRole(event.target.value as (typeof JOB_ROLES)[number])
    setShowSuggestions(false)
  }

  function handleAddSkill(skill: string) {
    setSkills((prev) => [...prev, skill])
  }

  function handleRemoveSkill(skill: string) {
    setSkills((prev) => prev.filter((item) => item !== skill))
  }

  function handleCvChange(event: ChangeEvent<HTMLInputElement>) {
    setCvFile(event.target.files?.[0] ?? null)
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
  }

  return (
    <main className="auth-page">
      <BackButton />
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
            onClick={() => setAccountType('candidate')}
          >
            Candidate
          </button>
          <button type="button" role="tab" aria-selected={false} className="auth-toggle auth-toggle-disabled" disabled>
            Recruiter
            <span className="auth-soon">Soon</span>
          </button>
        </div>

        <div className="auth-toggle-group" role="tablist" aria-label="Sign in or sign up">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'signin'}
            className={`auth-toggle ${mode === 'signin' ? 'auth-toggle-active' : ''}`}
            onClick={() => setMode('signin')}
          >
            Sign In
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'signup'}
            className={`auth-toggle ${mode === 'signup' ? 'auth-toggle-active' : ''}`}
            onClick={() => setMode('signup')}
          >
            Sign Up
          </button>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          {mode === 'signin' ? (
            <>
              <label className="field">
                <span className="field-label">Username</span>
                <Input type="text" name="username" placeholder="Enter your username" required />
              </label>
              <label className="field">
                <span className="field-label">Password</span>
                <Input type="password" name="password" placeholder="Enter your password" required />
              </label>
            </>
          ) : (
            <>
              <label className="field">
                <span className="field-label">Job Title / Role</span>
                <Select value={jobRole} onChange={handleJobRoleChange} required>
                  <option value="" disabled>
                    Select your role
                  </option>
                  {JOB_ROLES.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </Select>
              </label>

              <div className="field">
                <span className="field-label">Skillset</span>
                <div className="skillset-row">
                  <Select value={skillRole} onChange={handleSkillRoleChange}>
                    <option value="" disabled>
                      Select a role
                    </option>
                    {JOB_ROLES.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </Select>
                  <Button type="button" variant="secondary" disabled={!skillRole} onClick={() => setShowSuggestions(true)}>
                    Add Skills
                  </Button>
                </div>

                {showSuggestions && suggestedSkills.length > 0 && (
                  <div className="skill-suggestions">
                    <span className="skill-suggestions-label">Tap to add</span>
                    <div className="tag-list">
                      {suggestedSkills.map((skill) => (
                        <Tag key={skill} onClick={() => handleAddSkill(skill)}>
                          {skill}
                        </Tag>
                      ))}
                    </div>
                  </div>
                )}

                {skills.length > 0 && (
                  <div className="tag-list selected-skills">
                    {skills.map((skill) => (
                      <Tag key={skill} variant="active" onRemove={() => handleRemoveSkill(skill)}>
                        {skill}
                      </Tag>
                    ))}
                  </div>
                )}
              </div>

              <label className="field">
                <span className="field-label">Total Experience (years)</span>
                <Input
                  type="number"
                  name="experience"
                  min="0"
                  step="0.5"
                  placeholder="e.g. 2.5"
                  value={experience}
                  onChange={(event) => setExperience(event.target.value)}
                  required
                />
              </label>

              <div className="field">
                <span className="field-label">CV / Resume</span>
                <label className="file-input">
                  <input type="file" accept=".pdf,.doc,.docx" onChange={handleCvChange} hidden />
                  <span className="file-input-button">Choose File</span>
                  <span className="file-input-name">{cvFile ? cvFile.name : 'No file selected'}</span>
                </label>
              </div>
            </>
          )}

          <Button type="submit" variant="primary" className="auth-submit">
            {mode === 'signin' ? 'Sign In' : 'Create Account'}
          </Button>
        </form>
      </div>
    </main>
  )
}

export default Auth
