interface HeaderProps {
  title: string
}

function Header({ title }: HeaderProps) {
  return <h1>{title}</h1>
}

export default Header
