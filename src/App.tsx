import { useMemo, useState } from 'react'
import './App.css'

interface Task {
  id: number
  title: string
  done: boolean
}

let nextId = 3

const initialTasks: Task[] = [
  { id: 1, title: 'Bootstrap the Cloud Agent environment', done: true },
  { id: 2, title: 'Verify the app runs end to end', done: false },
]

export default function App() {
  const [tasks, setTasks] = useState<Task[]>(initialTasks)
  const [draft, setDraft] = useState('')

  const remaining = useMemo(
    () => tasks.filter((task) => !task.done).length,
    [tasks],
  )

  function addTask() {
    const title = draft.trim()
    if (!title) return
    setTasks((prev) => [...prev, { id: nextId++, title, done: false }])
    setDraft('')
  }

  function toggleTask(id: number) {
    setTasks((prev) =>
      prev.map((task) =>
        task.id === id ? { ...task, done: !task.done } : task,
      ),
    )
  }

  return (
    <main className="app">
      <header className="app__header">
        <span className="app__badge">cursor_2027</span>
        <h1>Environment Check</h1>
        <p className="app__subtitle">
          A tiny task list that proves the dev environment runs end to end.
        </p>
      </header>

      <section className="card">
        <div className="card__input-row">
          <input
            aria-label="New task"
            className="card__input"
            placeholder="Add a task…"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') addTask()
            }}
          />
          <button className="card__add" type="button" onClick={addTask}>
            Add
          </button>
        </div>

        <ul className="card__list">
          {tasks.map((task) => (
            <li key={task.id} className="task">
              <label className="task__label">
                <input
                  type="checkbox"
                  checked={task.done}
                  onChange={() => toggleTask(task.id)}
                />
                <span
                  className={task.done ? 'task__title task__title--done' : 'task__title'}
                >
                  {task.title}
                </span>
              </label>
            </li>
          ))}
        </ul>

        <footer className="card__footer">
          <span data-testid="remaining">{remaining}</span> task
          {remaining === 1 ? '' : 's'} remaining
        </footer>
      </section>
    </main>
  )
}
