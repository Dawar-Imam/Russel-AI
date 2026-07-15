import { useRef, useState } from 'react'
import AsyncCreatableSelect from 'react-select/async-creatable'
import type { GroupBase, InputActionMeta, OptionsOrGroups, StylesConfig } from 'react-select'
import '../css/TaxonomySelect.css'

export interface TaxonomyOption {
  value: number
  label: string
}

const TAXONOMY_NAME_RE = /^(?=.*[A-Za-z]).{2,100}$/
const LOAD_DEBOUNCE_MS = 250

function isValidTaxonomyName(name: string): boolean {
  return TAXONOMY_NAME_RE.test(name.trim())
}

function taxonomyStyles<IsMulti extends boolean>(): StylesConfig<TaxonomyOption, IsMulti, GroupBase<TaxonomyOption>> {
  return {
    control: (base, state) => ({
      ...base,
      minHeight: 42,
      backgroundColor: 'var(--color-surface-raised)',
      borderColor: state.isFocused ? 'var(--color-primary)' : 'var(--color-border)',
      borderRadius: 8,
      boxShadow: state.isFocused ? 'var(--shadow-focus-ring)' : 'none',
      cursor: 'text',
    }),
    menu: (base) => ({
      ...base,
      backgroundColor: 'var(--color-surface-raised)',
      border: '1px solid var(--color-border)',
      borderRadius: 8,
      overflow: 'hidden',
      zIndex: 20,
    }),
    menuList: (base) => ({ ...base, padding: 4 }),
    option: (base, state) => ({
      ...base,
      backgroundColor: state.isSelected
        ? 'var(--color-primary)'
        : state.isFocused
          ? 'var(--color-surface)'
          : 'transparent',
      color: state.isSelected ? 'var(--color-bg)' : 'var(--color-text-primary)',
      borderRadius: 6,
      cursor: 'pointer',
    }),
    singleValue: (base) => ({ ...base, color: 'var(--color-text-primary)' }),
    input: (base) => ({ ...base, color: 'var(--color-text-primary)' }),
    placeholder: (base) => ({ ...base, color: 'var(--color-text-secondary)' }),
    multiValue: (base) => ({ ...base, backgroundColor: 'var(--color-secondary)', borderRadius: 9999 }),
    multiValueLabel: (base) => ({ ...base, color: 'var(--color-info-text)' }),
    multiValueRemove: (base) => ({ ...base, borderRadius: 9999, color: 'var(--color-info-text)' }),
    indicatorSeparator: (base) => ({ ...base, backgroundColor: 'var(--color-border)' }),
    dropdownIndicator: (base) => ({ ...base, color: 'var(--color-text-secondary)' }),
    clearIndicator: (base) => ({ ...base, color: 'var(--color-text-secondary)' }),
    noOptionsMessage: (base) => ({ ...base, color: 'var(--color-text-secondary)' }),
    loadingMessage: (base) => ({ ...base, color: 'var(--color-text-secondary)' }),
  }
}

interface TaxonomySelectBaseProps {
  /** Server-side search — called (debounced) with the current input text. */
  loadOptions: (query: string) => Promise<TaxonomyOption[]>
  /** Persists a brand-new entry (e.g. via a get-or-create API call) and returns it. */
  onCreateOption: (name: string) => Promise<TaxonomyOption>
  placeholder?: string
  isDisabled?: boolean
  className?: string
  /** Optional pass-through for field-level validation on typed (uncommitted) text. */
  onInputChange?: (value: string, actionMeta: InputActionMeta) => void
  onBlur?: () => void
}

interface TaxonomySelectSingleProps extends TaxonomySelectBaseProps {
  isMulti?: false
  value: TaxonomyOption | null
  onChange: (value: TaxonomyOption | null) => void
}

interface TaxonomySelectMultiProps extends TaxonomySelectBaseProps {
  isMulti: true
  value: TaxonomyOption[]
  onChange: (value: TaxonomyOption[]) => void
  controlShouldRenderValue?: boolean
}

type TaxonomySelectProps = TaxonomySelectSingleProps | TaxonomySelectMultiProps

function TaxonomySelect(props: TaxonomySelectProps) {
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)
  const loadTimerRef = useRef<ReturnType<typeof setTimeout>>()

  function debouncedLoadOptions(query: string): Promise<TaxonomyOption[]> {
    return new Promise((resolve, reject) => {
      if (loadTimerRef.current) clearTimeout(loadTimerRef.current)
      loadTimerRef.current = setTimeout(() => {
        props.loadOptions(query).then(resolve, reject)
      }, LOAD_DEBOUNCE_MS)
    })
  }

  async function handleCreate(inputValue: string) {
    setCreateError(null)
    setCreating(true)
    try {
      const created = await props.onCreateOption(inputValue.trim())
      if (props.isMulti) {
        props.onChange([...props.value, created])
      } else {
        props.onChange(created)
      }
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : 'Failed to create entry')
    } finally {
      setCreating(false)
    }
  }

  const isValidNewOption = (
    inputValue: string,
    _value: unknown,
    options: OptionsOrGroups<TaxonomyOption, GroupBase<TaxonomyOption>>,
  ) =>
    isValidTaxonomyName(inputValue) &&
    !options.some((o) => 'value' in o && o.label.toLowerCase() === inputValue.trim().toLowerCase())

  return (
    <>
      {props.isMulti ? (
        <AsyncCreatableSelect<TaxonomyOption, true>
          className={props.className}
          classNamePrefix="taxonomy-select"
          isMulti
          isDisabled={props.isDisabled || creating}
          isLoading={creating}
          cacheOptions
          defaultOptions
          loadOptions={debouncedLoadOptions}
          onCreateOption={(inputValue) => void handleCreate(inputValue)}
          isValidNewOption={isValidNewOption}
          formatCreateLabel={(inputValue) => `Create "${inputValue.trim()}"`}
          noOptionsMessage={() => 'No matches'}
          placeholder={props.placeholder ?? 'Search…'}
          value={props.value}
          onChange={(selected) => props.onChange(selected ? [...selected] : [])}
          onInputChange={props.onInputChange}
          onBlur={props.onBlur}
          styles={taxonomyStyles<true>()}
          controlShouldRenderValue={props.controlShouldRenderValue ?? true}
        />
      ) : (
        <AsyncCreatableSelect<TaxonomyOption, false>
          className={props.className}
          classNamePrefix="taxonomy-select"
          isDisabled={props.isDisabled || creating}
          isLoading={creating}
          cacheOptions
          defaultOptions
          loadOptions={debouncedLoadOptions}
          onCreateOption={(inputValue) => void handleCreate(inputValue)}
          isValidNewOption={isValidNewOption}
          formatCreateLabel={(inputValue) => `Create "${inputValue.trim()}"`}
          noOptionsMessage={() => 'No matches'}
          placeholder={props.placeholder ?? 'Search…'}
          isClearable
          value={props.value}
          onChange={(selected) => props.onChange(selected ?? null)}
          onInputChange={props.onInputChange}
          onBlur={props.onBlur}
          styles={taxonomyStyles<false>()}
        />
      )}
      {createError && <span className="rd-field-error">{createError}</span>}
    </>
  )
}

export default TaxonomySelect
