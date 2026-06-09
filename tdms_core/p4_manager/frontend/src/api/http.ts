import axios from 'axios'

const http = axios.create({
  baseURL: '/api/mgr',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
})

export default http
