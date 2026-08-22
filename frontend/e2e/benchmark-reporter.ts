import type {
  FullResult,
  Reporter,
  TestCase,
  TestResult,
} from '@playwright/test/reporter'

class BenchmarkReporter implements Reporter {
  private result: string | undefined

  onTestEnd(_test: TestCase, result: TestResult) {
    const attachment = result.attachments.find(
      ({ name }) => name === 'benchmark-result',
    )
    if (attachment?.body) this.result = attachment.body.toString('utf8')
  }

  onEnd(result: FullResult) {
    if (this.result) {
      process.stdout.write(`${this.result}\n`)
      return
    }
    process.stdout.write(JSON.stringify({
      benchmark: 'automated-workflow-benchmark',
      error: `Benchmark did not complete (${result.status}).`,
    }) + '\n')
  }
}

export default BenchmarkReporter
