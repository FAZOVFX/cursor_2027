import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the environment check heading', () => {
    render(<App />)
    expect(
      screen.getByRole('heading', { name: /environment check/i }),
    ).toBeInTheDocument()
  })

  it('adds a new task and updates the remaining count', async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(screen.getByTestId('remaining')).toHaveTextContent('1')

    await user.type(screen.getByLabelText(/new task/i), 'Ship it')
    await user.click(screen.getByRole('button', { name: /add/i }))

    expect(screen.getByText('Ship it')).toBeInTheDocument()
    expect(screen.getByTestId('remaining')).toHaveTextContent('2')
  })

  it('toggles a task as done and decrements the remaining count', async () => {
    const user = userEvent.setup()
    render(<App />)

    const checkbox = screen.getByRole('checkbox', {
      name: /verify the app runs end to end/i,
    })
    expect(screen.getByTestId('remaining')).toHaveTextContent('1')

    await user.click(checkbox)

    expect(screen.getByTestId('remaining')).toHaveTextContent('0')
  })
})
