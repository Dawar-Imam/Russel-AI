import '../css/Header.css'

interface HeaderProps {
  title: string
}

function Header({ title }: HeaderProps) {
  return <h1 className="header-title">{title}</h1>
}

export default Header
